"""
Minimal fitz-compatible adapter backed by the PDFium engine via pypdfium2.

The cutoff extractor was originally developed and validated against this
PDFium-backed API. Keeping the adapter explicit prevents the production
runtime from silently switching to a different PDF text extraction engine.

Implements the subset of the PyMuPDF-style API used by cutoff_extractor.py:
  - fitz.open(path) -> Document
  - Document: len(), doc[i], doc.close()
  - Page.get_text("text") -> str
  - Page.get_pixmap(matrix=..., alpha=False) -> Pixmap (width, height, samples)
  - fitz.Matrix(scale, scale)
"""
import pypdfium2 as pdfium


class Matrix:
    def __init__(self, sx, sy=None):
        self.sx = sx
        self.sy = sy if sy is not None else sx


class Pixmap:
    def __init__(self, pil_image):
        pil_image = pil_image.convert("RGB")
        self.width, self.height = pil_image.size
        self.samples = pil_image.tobytes()


class Page:
    def __init__(self, pdfium_page):
        self._page = pdfium_page

    def get_text(self, kind="text"):
        tp = self._page.get_textpage()
        try:
            return tp.get_text_range()
        finally:
            tp.close()

    def get_pixmap(self, matrix=None, alpha=False):
        scale = matrix.sx if matrix is not None else 1.0
        bitmap = self._page.render(scale=scale)
        pil_image = bitmap.to_pil()
        return Pixmap(pil_image)


class Document:
    def __init__(self, path):
        self._doc = pdfium.PdfDocument(str(path))
        self._pages = [Page(self._doc[i]) for i in range(len(self._doc))]

    def __len__(self):
        return len(self._pages)

    def __getitem__(self, idx):
        return self._pages[idx]

    def close(self):
        try:
            self._doc.close()
        except Exception:
            pass


def open(path):  # noqa: A001 - mirror fitz.open API
    return Document(path)
