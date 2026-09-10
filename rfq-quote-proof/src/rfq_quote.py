"""RFQ -> quotation-draft matching engine (REVENUE work packet:
buyer/rfq-quote-proof-v0.1).

Deterministic, local, stdlib-only pipeline for one bounded case: a
text-based PDF RFQ for electrical parts, matched only against a supplied
product catalogue and an approved price list, producing a quotation draft
split into a clean "Quote" sheet and a "Review" sheet.

Pipeline: extract RFQ line items from a text-based PDF (reusing
money_machine.raw_evidence_intake's pdftotext extraction) -> load the
catalogue/approved-price CSV fixtures -> match each RFQ line by exact
product code -> flag anything the match cannot resolve with certainty
(unknown code, ambiguous catalogue code, unit mismatch, no approved price,
an available-but-unconfirmed substitution, a duplicated RFQ line) -> emit a
QuoteResult that a human reviews before any figure is sent to a buyer.

This module never guesses. It does not do fuzzy/OCR text matching, does not
convert units, and never silently substitutes one product code for another
-- every one of those situations is surfaced as a review reason instead.
Nothing here sends, publishes, or prices anything on its own authority.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pdf_extract import RawExtractionError, extract_pdf_units

REASON_UNKNOWN_CODE = "unknown_code"
REASON_AMBIGUOUS_CATALOGUE_CODE = "ambiguous_catalogue_code"
REASON_AMBIGUOUS_SUBSTITUTION = "ambiguous_substitution"
REASON_UNIT_MISMATCH = "unit_mismatch"
REASON_UNAPPROVED_PRICE = "unapproved_price"
REASON_SUBSTITUTION_AVAILABLE = "substitution_available"
REASON_DUPLICATE_LINE_CODE = "duplicate_line_code"

STATUS_MATCHED = "matched"
STATUS_NEEDS_REVIEW = "needs_review"

_ROW_PATTERN = re.compile(
    r"^\s*(?P<line_no>\d+)\s*\|\s*(?P<code>[^|]+?)\s*\|\s*(?P<description>[^|]+?)\s*"
    r"\|\s*(?P<qty>[^|]+?)\s*\|\s*(?P<unit>[^|]+?)\s*$"
)
_QTY_PATTERN = re.compile(r"^[0-9][0-9,]*(\.[0-9]+)?$")


class RfqParseError(ValueError):
    """Raised when a recognizable RFQ table row cannot be parsed deterministically."""


class CatalogueError(ValueError):
    """Raised when the catalogue or approved price list fixture is malformed
    or internally ambiguous in a way that must fail closed rather than
    silently pick a row."""


def _norm(value: str) -> str:
    return value.strip().upper()


def _parse_qty(raw: str, *, context: str) -> Decimal:
    cleaned = raw.strip()
    if not _QTY_PATTERN.match(cleaned):
        raise RfqParseError(f"unparseable quantity {raw!r} in {context}")
    try:
        return Decimal(cleaned.replace(",", ""))
    except InvalidOperation as exc:
        raise RfqParseError(f"unparseable quantity {raw!r} in {context}") from exc


@dataclass(frozen=True)
class RfqLine:
    """One parsed RFQ table row with provenance back to its PDF page."""

    source_file: str
    source_location: str
    line_no: int
    product_code: str
    description: str
    qty: Decimal
    unit: str
    raw_text: str


@dataclass(frozen=True)
class CatalogueItem:
    product_code: str
    description: str
    unit: str
    substitute_for: str | None
    source_row: int


@dataclass(frozen=True)
class PriceEntry:
    product_code: str
    unit: str
    unit_price: Decimal
    currency: str
    source_row: int


@dataclass(frozen=True)
class QuoteLine:
    """One resolved RFQ line: either cleanly matched, or carrying one or more
    machine-readable reasons a human must resolve before it can be quoted."""

    rfq_line: RfqLine
    status: str
    reasons: tuple[str, ...]
    matched_code: str | None = None
    matched_description: str | None = None
    matched_unit: str | None = None
    unit_price: Decimal | None = None
    currency: str | None = None
    line_total: Decimal | None = None
    suggested_code: str | None = None
    suggested_description: str | None = None


@dataclass
class QuoteResult:
    quote_lines: list[QuoteLine] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        counts["total_lines"] = len(self.quote_lines)
        for ql in self.quote_lines:
            counts[ql.status] += 1
            for reason in ql.reasons:
                counts[f"reason:{reason}"] += 1
        return dict(counts)

    def quote_rows(self) -> list[list]:
        header = [
            "RFQ Line",
            "Product Code",
            "Description",
            "Qty",
            "Unit",
            "Unit Price",
            "Currency",
            "Line Total",
        ]
        rows: list[list] = [header]
        for ql in self.quote_lines:
            if ql.status != STATUS_MATCHED:
                continue
            rows.append(
                [
                    ql.rfq_line.line_no,
                    ql.matched_code,
                    ql.matched_description,
                    ql.rfq_line.qty,
                    ql.matched_unit,
                    ql.unit_price,
                    ql.currency,
                    ql.line_total,
                ]
            )
        return rows

    def review_rows(self) -> list[list]:
        header = [
            "RFQ Line",
            "Requested Code",
            "Requested Description",
            "Qty",
            "Requested Unit",
            "Reasons",
            "Suggested Code",
            "Suggested Description",
            "Source",
        ]
        rows: list[list] = [header]
        for ql in self.quote_lines:
            if ql.status != STATUS_NEEDS_REVIEW:
                continue
            rows.append(
                [
                    ql.rfq_line.line_no,
                    ql.rfq_line.product_code,
                    ql.rfq_line.description,
                    ql.rfq_line.qty,
                    ql.rfq_line.unit,
                    ", ".join(ql.reasons),
                    ql.suggested_code,
                    ql.suggested_description,
                    f"{ql.rfq_line.source_file}:{ql.rfq_line.source_location}",
                ]
            )
        return rows


def parse_rfq_pdf(path: str | Path) -> list[RfqLine]:
    """Extract RFQ table rows from a text-based PDF.

    Only lines shaped like `<line_no> | <code> | <description> | <qty> |
    <unit>` (an integer line number, exactly four pipe separators) are
    treated as table rows; prose/header/footer lines are ignored. A line
    that has that shape but an unparseable quantity fails the whole run
    closed rather than silently dropping a buyer's line item.
    """
    path = Path(path)
    units = extract_pdf_units(path, path.name)
    lines: list[RfqLine] = []
    for unit in units:
        for raw_text in unit.text.splitlines():
            match = _ROW_PATTERN.match(raw_text)
            if not match:
                continue
            line_no = int(match.group("line_no"))
            context = f"{path.name}:{unit.source_location} (RFQ line {line_no})"
            qty = _parse_qty(match.group("qty"), context=context)
            lines.append(
                RfqLine(
                    source_file=path.name,
                    source_location=unit.source_location,
                    line_no=line_no,
                    product_code=match.group("code").strip(),
                    description=match.group("description").strip(),
                    qty=qty,
                    unit=match.group("unit").strip(),
                    raw_text=raw_text.strip(),
                )
            )
    return lines


def load_catalogue_csv(path: str | Path) -> list[CatalogueItem]:
    """Load `product_code,description,unit,substitute_for` rows.
    `substitute_for` may be blank. Duplicate product codes are loaded as
    distinct rows -- ambiguity is a matching-time review flag, not a load
    error, so a real catalogue data-quality problem is surfaced rather than
    hidden."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines())
    required = {"product_code", "description", "unit", "substitute_for"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise CatalogueError(f"catalogue CSV {path.name} missing required columns {sorted(required)}")
    items = []
    for row_number, row in enumerate(reader, start=2):
        code = (row["product_code"] or "").strip()
        if not code:
            raise CatalogueError(f"catalogue CSV {path.name} row {row_number} has an empty product_code")
        substitute_for = (row.get("substitute_for") or "").strip() or None
        items.append(
            CatalogueItem(
                product_code=code,
                description=(row["description"] or "").strip(),
                unit=(row["unit"] or "").strip(),
                substitute_for=substitute_for,
                source_row=row_number,
            )
        )
    return items


def load_price_list_csv(path: str | Path) -> list[PriceEntry]:
    """Load `product_code,unit,unit_price,currency` rows -- the approved
    price list. A duplicate (product_code, unit) pair with a different
    price fails the load closed: two conflicting approved prices for the
    same line is a data-integrity error, not something a matcher should
    pick between silently."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines())
    required = {"product_code", "unit", "unit_price", "currency"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise CatalogueError(f"price list CSV {path.name} missing required columns {sorted(required)}")
    entries: list[PriceEntry] = []
    seen: dict[tuple[str, str], PriceEntry] = {}
    for row_number, row in enumerate(reader, start=2):
        code = (row["product_code"] or "").strip()
        unit = (row["unit"] or "").strip()
        if not code or not unit:
            raise CatalogueError(f"price list CSV {path.name} row {row_number} has an empty product_code/unit")
        try:
            price = Decimal((row["unit_price"] or "").strip())
        except InvalidOperation as exc:
            raise CatalogueError(
                f"price list CSV {path.name} row {row_number} has an unparseable unit_price {row['unit_price']!r}"
            ) from exc
        key = (_norm(code), _norm(unit))
        entry = PriceEntry(
            product_code=code,
            unit=unit,
            unit_price=price,
            currency=(row["currency"] or "").strip(),
            source_row=row_number,
        )
        if key in seen and seen[key].unit_price != price:
            raise CatalogueError(
                f"price list CSV {path.name} has conflicting approved prices for {code}/{unit}: "
                f"row {seen[key].source_row} says {seen[key].unit_price}, row {row_number} says {price}"
            )
        seen[key] = entry
        entries.append(entry)
    return entries


def _index_catalogue(
    catalogue: list[CatalogueItem],
) -> tuple[dict[str, list[CatalogueItem]], dict[str, list[CatalogueItem]]]:
    by_code: dict[str, list[CatalogueItem]] = defaultdict(list)
    by_substitute: dict[str, list[CatalogueItem]] = defaultdict(list)
    for item in catalogue:
        by_code[_norm(item.product_code)].append(item)
        if item.substitute_for:
            by_substitute[_norm(item.substitute_for)].append(item)
    return by_code, by_substitute


def _index_prices(price_list: list[PriceEntry]) -> dict[tuple[str, str], PriceEntry]:
    by_key: dict[tuple[str, str], PriceEntry] = {}
    for entry in price_list:
        by_key[(_norm(entry.product_code), _norm(entry.unit))] = entry
    return by_key


def build_quote(
    rfq_lines: list[RfqLine],
    catalogue: list[CatalogueItem],
    price_list: list[PriceEntry],
) -> QuoteResult:
    """Resolve every RFQ line against the catalogue + approved price list.
    A line is `matched` only when: the product code resolves to exactly one
    catalogue row, the requested unit equals that row's catalogue unit, an
    approved price exists for that exact (code, unit), and the code was not
    requested on more than one RFQ line. Every other case is `needs_review`
    with one or more machine-readable reasons -- nothing is auto-resolved.
    """
    by_code, by_substitute = _index_catalogue(catalogue)
    price_by_key = _index_prices(price_list)

    code_counts: dict[str, int] = defaultdict(int)
    for rfq_line in rfq_lines:
        code_counts[_norm(rfq_line.product_code)] += 1

    quote_lines: list[QuoteLine] = []
    for rfq_line in rfq_lines:
        code_norm = _norm(rfq_line.product_code)
        reasons: list[str] = []
        matched_item: CatalogueItem | None = None
        suggested_code: str | None = None
        suggested_description: str | None = None

        matches = by_code.get(code_norm, [])
        if len(matches) == 1:
            matched_item = matches[0]
        elif len(matches) > 1:
            reasons.append(REASON_AMBIGUOUS_CATALOGUE_CODE)
        else:
            substitutes = by_substitute.get(code_norm, [])
            if len(substitutes) == 1:
                reasons.append(REASON_SUBSTITUTION_AVAILABLE)
                suggested_code = substitutes[0].product_code
                suggested_description = substitutes[0].description
            elif len(substitutes) > 1:
                reasons.append(REASON_AMBIGUOUS_SUBSTITUTION)
            else:
                reasons.append(REASON_UNKNOWN_CODE)

        unit_price: Decimal | None = None
        currency: str | None = None
        if matched_item is not None:
            if _norm(rfq_line.unit) != _norm(matched_item.unit):
                reasons.append(REASON_UNIT_MISMATCH)
            else:
                price_entry = price_by_key.get((code_norm, _norm(matched_item.unit)))
                if price_entry is None:
                    reasons.append(REASON_UNAPPROVED_PRICE)
                else:
                    unit_price = price_entry.unit_price
                    currency = price_entry.currency

        if code_counts[code_norm] > 1:
            reasons.append(REASON_DUPLICATE_LINE_CODE)

        if reasons:
            quote_lines.append(
                QuoteLine(
                    rfq_line=rfq_line,
                    status=STATUS_NEEDS_REVIEW,
                    reasons=tuple(reasons),
                    matched_code=matched_item.product_code if matched_item else None,
                    matched_description=matched_item.description if matched_item else None,
                    matched_unit=matched_item.unit if matched_item else None,
                    suggested_code=suggested_code,
                    suggested_description=suggested_description,
                )
            )
        else:
            line_total = rfq_line.qty * unit_price
            quote_lines.append(
                QuoteLine(
                    rfq_line=rfq_line,
                    status=STATUS_MATCHED,
                    reasons=(),
                    matched_code=matched_item.product_code,
                    matched_description=matched_item.description,
                    matched_unit=matched_item.unit,
                    unit_price=unit_price,
                    currency=currency,
                    line_total=line_total,
                )
            )

    return QuoteResult(quote_lines=quote_lines)
