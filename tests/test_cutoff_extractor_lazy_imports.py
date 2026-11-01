from __future__ import annotations

from pathlib import Path

import pytest

from scripts import cutoff_extractor


class _Page:
    def __init__(self, text: str):
        self.text = text

    def get_text(self, _kind: str) -> str:
        return self.text


class _Document:
    def __init__(self, pages: list[str]):
        self.pages = [_Page(page) for page in pages]

    def __len__(self) -> int:
        return len(self.pages)

    def __getitem__(self, index: int) -> _Page:
        return self.pages[index]


def test_native_text_quality_skips_optional_ocr_initialization(monkeypatch):
    def unexpected_ocr_load():
        pytest.fail("OCR dependencies should not load when native text is sufficient")

    monkeypatch.setattr(cutoff_extractor, "_ensure_ocr_loaded", unexpected_ocr_load)
    doc = _Document(["GOPENH 12345 (99.50)"] * 5)

    technique, scores = cutoff_extractor.choose_extraction_technique(
        doc, dpi=300, lang="eng"
    )

    assert technique == "native"
    assert scores["native"] > 0


def test_ocr_page_reports_missing_optional_dependencies(monkeypatch):
    monkeypatch.setattr(cutoff_extractor, "_ensure_ocr_loaded", lambda: False)

    with pytest.raises(RuntimeError, match="optional OCR dependencies"):
        cutoff_extractor.ocr_page(_Page(""), dpi=300)
