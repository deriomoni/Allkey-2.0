"""Column recognition for the опись Excel import.

Real accountants' files name columns freely («Товар», «Номенклатура», «Кол-во»,
«Цена за ед.», «Цена, тг», «Сумма»), and 1С exports put the org name, period and
blank rows above the header. So we:
  * match column titles against SYNONYMS (extend this dict — no code change);
  * normalize titles (lowercase, drop punctuation, collapse spaces) before match;
  * scan several top rows to find the header, not just row 0.

If auto-detection fails the caller shows a manual column-mapping screen rather
than rejecting the file.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Category -> substring synonyms (matched against the normalized title).
# Extend freely; order of CATEGORY_PRIORITY decides ties (a title matching two).
COLUMN_SYNONYMS: Dict[str, List[str]] = {
    "name": ["наимен", "назв", "товар", "номенклат", "ценност", "материал", "предмет", "актив"],
    "qty": ["кол", "количество", "колво", "штук", "шт"],
    "price": ["цена", "стоим", "цена за ед", "цена ед"],
    "sum": ["сумма", "итог"],
    "code": ["код", "номер", "инвентарн", "инв", "артикул", "номенклатурный"],
    "unit": ["ед изм", "единиц", "ед"],
}

# A title matching several categories is assigned to the first here.
CATEGORY_PRIORITY = ["name", "qty", "price", "sum", "code", "unit"]

_NON_ALNUM = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)


def normalize(text) -> str:
    """Lowercase, replace punctuation/extra spaces with a single space."""
    s = str(text if text is not None else "").lower().strip()
    s = _NON_ALNUM.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def classify(title) -> Optional[str]:
    """Return the category for one column title, or None."""
    n = normalize(title)
    if not n:
        return None
    for category in CATEGORY_PRIORITY:
        for syn in COLUMN_SYNONYMS[category]:
            if syn in n:
                return category
    return None


def map_row(row) -> Dict[str, int]:
    """Map a header row's cells to categories → column index (first column wins)."""
    mapping: Dict[str, int] = {}
    for ci, cell in enumerate(row):
        cat = classify(cell)
        if cat and cat not in mapping:
            mapping[cat] = ci
    return mapping


def find_header(rows, max_scan: int = 20) -> Tuple[Optional[int], Optional[Dict[str, int]]]:
    """Find the header row: the first row (within max_scan) whose columns map to at
    least name + qty + price. Returns (row_index, mapping) or (None, None)."""
    for i, row in enumerate(rows[:max_scan]):
        mapping = map_row(row)
        if {"name", "qty", "price"} <= mapping.keys():
            return i, mapping
    return None, None


def guess_header_row(rows, max_scan: int = 20) -> int:
    """Best-effort header row for the manual-mapping screen: prefer rows with more
    recognizable titles, then more non-empty cells. 1С preamble rows (org name,
    period) have few non-empty cells and no matches, so they lose."""
    best_i, best_score = 0, -1
    for i, row in enumerate(rows[:max_scan]):
        nonempty = sum(1 for c in row if normalize(c))
        matches = sum(1 for c in row if classify(c))
        score = matches * 100 + nonempty
        if nonempty >= 2 and score > best_score:
            best_i, best_score = i, score
    return best_i
