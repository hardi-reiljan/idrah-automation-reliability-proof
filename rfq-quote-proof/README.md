# RFQ → Quote Proof v0.1

**Status:** self-owned synthetic engineering proof. Not client work. Not a production deployment.

This bounded proof was built against a public RFQ-to-quote prototype request for electrical-parts distributors. It demonstrates one narrow path:

`text PDF RFQ → line extraction → catalogue/approved-price match → human review for uncertainty → Excel quotation draft`

## What is included

- `input/rfq.pdf` — synthetic text-based electrical-parts RFQ
- `input/catalogue.csv` — synthetic supplied catalogue
- `input/price_list.csv` — synthetic approved price list
- `src/rfq_quote.py` — deterministic parsing and match logic
- `src/pdf_extract.py` — local `pdfinfo` / `pdftotext` extraction with page-count checks
- `src/xlsx_writer.py` — minimal stdlib XLSX writer
- `demo.py` — one-command local demonstration
- `workflow/rfq-quote-proof-v0.1.workflow.json` — importable n8n workflow
- `output/quotation_draft.xlsx` — generated Quote + Review workbook

## Safety / authority behavior

Prices come only from the approved price list. Exact catalogue codes are matched first. Unknown codes, unit mismatches, ambiguous catalogue codes, unapproved prices, duplicate RFQ line codes, and proposed substitutions are sent to review instead of being silently accepted.

No OCR, ERP integration, automatic email sending, dashboard, fuzzy product substitution, automatic unit conversion, or customer data is included.

## Runtime validation — 2026-09-10

Python proof:
- targeted RFQ/n8n tests: **20 passed**
- full Money Machine suite after the isolated proof build: **874 passed**
- generated XLSX validated as a well-formed OOXML ZIP

n8n proof:
- runtime: n8n `2.36.9`, Node.js `24.20.0`
- workflow import: PASS
- workflow publish in isolated local instance: PASS
- exact approved-price match: HTTP 200 / `matched` — PASS
- unknown product code: HTTP 202 / `needs_review` — PASS
- unit mismatch: HTTP 202 / `needs_review` — PASS

Example matched case: `CB-16A-1P`, qty 10 pcs → approved unit price EUR 1.85 → line total EUR 18.50.

## Run locally

Requires Python 3 plus Poppler CLI tools (`pdfinfo`, `pdftotext`). No Python package installation is required.

```bash
python3 rfq-quote-proof/demo.py
```

## Claim boundary

This supports the claim that I built and runtime-validated a self-owned RFQ-to-quote proof with deterministic document extraction, approved-price matching, human-review routing, n8n orchestration, and Excel output.

It does **not** support claims of prior client RFQ deployments, production scale, customer data handling, or years of n8n experience.
