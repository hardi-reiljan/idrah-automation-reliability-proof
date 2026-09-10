from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

class RawExtractionError(ValueError):
    pass

@dataclass(frozen=True)
class RawUnit:
    source_file: str
    source_location: str
    text: str

def _pdf_page_count(path: Path) -> int:
    proc = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RawExtractionError(f"pdfinfo failed for {path.name}: {proc.stderr.strip()}")
    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RawExtractionError(f"pdfinfo output for {path.name} had no Pages: line")

def extract_pdf_units(path: Path, rel_name: str) -> list[RawUnit]:
    expected_pages = _pdf_page_count(path)
    proc = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RawExtractionError(f"pdftotext failed for {rel_name}: {proc.stderr.strip()}")
    pages = proc.stdout.split("\x0c")
    if pages and pages[-1] == "":
        pages = pages[:-1]
    if len(pages) != expected_pages:
        raise RawExtractionError(f"page count mismatch for {rel_name}: pdfinfo={expected_pages}, pdftotext={len(pages)}")
    return [RawUnit(rel_name, f"page {i}", text) for i, text in enumerate(pages, start=1)]
