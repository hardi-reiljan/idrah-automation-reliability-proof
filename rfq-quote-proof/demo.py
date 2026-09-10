#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from rfq_quote import build_quote, load_catalogue_csv, load_price_list_csv, parse_rfq_pdf
from xlsx_writer import write_xlsx

rfq_lines = parse_rfq_pdf(ROOT / "input/rfq.pdf")
catalogue = load_catalogue_csv(ROOT / "input/catalogue.csv")
prices = load_price_list_csv(ROOT / "input/price_list.csv")
result = build_quote(rfq_lines, catalogue, prices)
write_xlsx(ROOT / "output/quotation_draft.xlsx", {"Quote": result.quote_rows(), "Review": result.review_rows()})
print(result.summary())
