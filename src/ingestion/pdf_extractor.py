"""PDF to text extraction implementing the ``DocumentExtractor`` port."""

from __future__ import annotations

from ingestion.ports import Attachment


class PdfTextExtractor:
    """Extracts plain text from a PDF attachment using pypdfium2."""

    def extract(self, attachment: Attachment) -> str:
        if "pdf" not in attachment.content_type.lower() and not attachment.filename.lower().endswith(".pdf"):
            return attachment.data.decode("utf-8", errors="replace")
        return self._extract_pdf(attachment.data)

    @staticmethod
    def _extract_pdf(data: bytes) -> str:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(data)
        try:
            chunks: list[str] = []
            for page in document:
                text_page = page.get_textpage()
                chunks.append(text_page.get_text_range())
            return "\n".join(chunks)
        finally:
            document.close()
