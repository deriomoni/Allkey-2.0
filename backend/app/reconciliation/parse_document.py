"""
Parse document field from settlement acts into components:
doc_type, doc_number, doc_date using DATE as the sole anchor.

Algorithm:
1. Find all dates (dd.mm.yy or dd.mm.yyyy) in the string
2. Number = last alphanumeric token LEFT of first date
3. Type = everything left of number
4. Extra number/date from second date (for payment orders)
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedDocument:
    doc_type: Optional[str]
    doc_number: Optional[str]
    doc_date: Optional[str]
    extra_number: Optional[str]
    extra_date: Optional[str]
    parsed: bool


# Matches dd.mm.yy or dd.mm.yyyy
DATE_RE = re.compile(r'\d{1,2}\.\d{2}\.\d{2,4}')

# Trailing junk between number and date: "от", commas, brackets, №, spaces
JUNK_TRAIL_RE = re.compile(r'[\s,\(\)№]*(?:\bот\b|\bна\b)?[\s,\(\)№]*$')

# Valid document number: alphanumeric with hyphens, must contain at least one digit
NUMBER_TOKEN_RE = re.compile(r'^[A-Za-z0-9А-Яа-яЁё\-]+$')

# For short strings without date: extract trailing digits (e.g. "пп476" → "476")
SHORT_CODE_RE = re.compile(r'(\d[\d\-]*)$')


def parse_document_field(raw: str) -> ParsedDocument:
    """Parse a document string into type, number, date components."""
    # Step 0: normalize
    text = raw.strip()
    text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00a0]', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    if not text:
        return ParsedDocument(None, None, None, None, None, parsed=False)

    # Step 1: find all dates
    dates = [(m.group(), m.start(), m.end()) for m in DATE_RE.finditer(text)]

    if not dates:
        # Fallback for short codes without date: "пп476", "Реализация 28", "20П0011617"
        tokens = text.split()
        if len(tokens) == 1:
            # Single token: if it has digits, it's a number (strip leading prefixes)
            candidate = tokens[0].lstrip('№')
            if candidate and re.search(r'\d', candidate):
                # Check if it's a pure code (mixed letters+digits like "20П0011617", "пп476")
                # Split prefix letters from number only if prefix is all-letters
                m = re.match(r'^([а-яА-ЯёЁa-zA-Z]+)(\d[\d\-]*)$', candidate)
                if m:
                    return ParsedDocument(
                        doc_type=m.group(1), doc_number=m.group(2), doc_date=None,
                        extra_number=None, extra_date=None, parsed=False
                    )
                return ParsedDocument(
                    doc_type=None, doc_number=candidate, doc_date=None,
                    extra_number=None, extra_date=None, parsed=False
                )
        elif len(tokens) >= 2:
            # Multiple tokens: last token with digits = number, rest = type
            candidate = tokens[-1].lstrip('№')
            if candidate and re.search(r'\d', candidate):
                doc_type = ' '.join(tokens[:-1]).rstrip('№').strip()
                return ParsedDocument(
                    doc_type=doc_type or None, doc_number=candidate, doc_date=None,
                    extra_number=None, extra_date=None, parsed=False
                )
        return ParsedDocument(
            doc_type=text, doc_number=None, doc_date=None,
            extra_number=None, extra_date=None, parsed=False
        )

    main_date, date_start, date_end = dates[0]

    # Step 2: find number — left of first date
    left = text[:date_start]
    left_cleaned = JUNK_TRAIL_RE.sub('', left).strip()

    doc_number = None
    doc_type = left_cleaned

    tokens = left_cleaned.split()
    if tokens:
        candidate = tokens[-1].lstrip('№')
        if candidate and NUMBER_TOKEN_RE.match(candidate) and re.search(r'\d', candidate):
            doc_number = candidate
            doc_type = ' '.join(tokens[:-1]).rstrip('№').strip()

    # Step 3: extra number/date (second date)
    extra_number = None
    extra_date = None
    if len(dates) > 1:
        extra_date_val, extra_date_start, _ = dates[1]
        extra_date = extra_date_val
        tail = text[date_end:extra_date_start]
        tail_cleaned = JUNK_TRAIL_RE.sub('', tail).strip()
        # Remove "вх." prefix and "№" from tail tokens
        tail_cleaned = re.sub(r'\bвх\.?\s*', '', tail_cleaned).strip()
        tail_tokens = tail_cleaned.split()
        if tail_tokens:
            candidate = tail_tokens[-1].lstrip('№')
            if candidate and re.search(r'\d', candidate):
                extra_number = candidate

    return ParsedDocument(
        doc_type=doc_type or None,
        doc_number=doc_number,
        doc_date=main_date,
        extra_number=extra_number,
        extra_date=extra_date,
        parsed=True
    )


if __name__ == '__main__':
    test_cases = [
        "Реализация ТМЗ и услуг 1498 от 02.09.2025",
        "Приходная накладная №1498 от 02.09.2025",
        "Расходная накладная №1-00017436  от 10.09.2025",
        "Списание со счета №1S-0006960 от 04.09.2025",
        "Платежное поручение (входящее) 559 от 04.09.2025,  № вх. 17024558 от 04.09.2025",
        "Сальдо на 01.09.2025",
        "Накладная №1498 02.09.2025",
        "Счёт 1498, 02.09.2025",
        "Счёт 1498 (02.09.2025)",
        "",
        "Просто текст без даты",
        "01.09.2025",
        # Short codes without date (counterparty format)
        "пп476",
        "Реализация 28",
        "20П0011617",
        "4642",
    ]

    for raw in test_cases:
        result = parse_document_field(raw)
        print(f"INPUT:  {raw!r}")
        print(f"OUTPUT: type={result.doc_type!r}, number={result.doc_number!r}, "
              f"date={result.doc_date!r}, extra_num={result.extra_number!r}, "
              f"extra_date={result.extra_date!r}, parsed={result.parsed}")
        print()
