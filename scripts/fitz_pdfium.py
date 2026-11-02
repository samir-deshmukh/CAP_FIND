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
    """Minimal fitz.Matrix-compatible scale holder for PDFium rendering."""
    def __init__(self, sx, sy=None):
        """Store horizontal and vertical render scales."""
        self.sx = sx
        self.sy = sy if sy is not None else sx


class Pixmap:
    """Expose a rendered Pillow image through the fitz Pixmap fields used by the extractor."""
    def __init__(self, pil_image):
        """Convert the rendered image to RGB and expose its dimensions and raw bytes."""
        pil_image = pil_image.convert("RGB")
        self.width, self.height = pil_image.size
        self.samples = pil_image.tobytes()


class Page:
    """Wrap one PDFium page with the small fitz-style API used by cutoff_extractor."""
    def __init__(self, pdfium_page):
        """Keep the underlying PDFium page for text and image rendering."""
        self._page = pdfium_page

    def get_text(self, kind="text"):
        """Extract the page's native text and always close its temporary text page."""
        tp = self._page.get_textpage()
        try:
            return tp.get_text_range()
        finally:
            tp.close()

    def get_pixmap(self, matrix=None, alpha=False):
        """Render the page at the requested scale and return a fitz-like Pixmap."""
        scale = matrix.sx if matrix is not None else 1.0
        bitmap = self._page.render(scale=scale)
        pil_image = bitmap.to_pil()
        return Pixmap(pil_image)


class Document:
    """Wrap a PDFium document and expose indexed Page objects like fitz.open()."""
    def __init__(self, path):
        """Open the source PDF and create lightweight wrappers for its pages."""
        self._doc = pdfium.PdfDocument(str(path))
        self._pages = [Page(self._doc[i]) for i in range(len(self._doc))]

    def __len__(self):
        """Return the number of pages in the source PDF."""
        return len(self._pages)

    def __getitem__(self, idx):
        """Return the wrapped page at the requested zero-based index."""
        return self._pages[idx]

    def close(self):
        """Close the underlying PDFium document and release its resources."""
        try:
            self._doc.close()
        except Exception:
            pass


def open(path):  # noqa: A001 - mirror fitz.open API
    """Open a PDF and return the fitz-compatible PDFium Document wrapper.

    Connections: cutoff_extractor.py imports this adapter as its PDF engine when configured for PDFium.
    """
    return Document(path)
