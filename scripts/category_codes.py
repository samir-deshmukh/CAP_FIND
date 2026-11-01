"""Shared syntax checks for source-provided CAP category codes.

Reference CSVs provide human-readable labels for known categories; they are
not an exhaustive list of category codes that future CAP PDFs may introduce.
"""

import re


_CATEGORY_CODE = re.compile(r"^(?:[GL])?[A-Z][A-Z0-9]*(?:[-/][A-Z0-9]+)*$")


def is_category_code(value: str) -> bool:
    """Accept a bounded category token, including future codes absent from
    the current reference table, while rejecting ordinary PDF text bleed.
    """
    normalized = str(value or "").strip().upper()
    return len(normalized) <= 32 and bool(_CATEGORY_CODE.fullmatch(normalized))
