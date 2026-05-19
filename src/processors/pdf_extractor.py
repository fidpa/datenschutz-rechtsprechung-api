"""
PDF-Textextraktion für Datenschutz-Rechtsprechung API.

Verwendet pdfplumber als primäre Methode mit Fallbacks für problematische PDFs.
Unterstützt max. 10MB und 100 Seiten (konfigurierbar).
"""

import os
import tempfile
import hashlib
from typing import Optional, Dict, Any
import subprocess

import httpx
import structlog
from pdfplumber import PDF
from pypdf import PdfReader

from src.config import settings

logger = structlog.get_logger()


class PDFExtractor:
    """Extrahiert Text aus PDF-Dokumenten mit mehreren Fallback-Methoden."""

    def __init__(self):
        self.max_size_mb = settings.max_pdf_size_mb
        self.max_pages = settings.pdf_max_pages
        self.timeout_seconds = getattr(settings, "pdf_timeout_seconds", 30)

    async def extract_from_url(self, url: str) -> Dict[str, Any]:
        """
        Lädt PDF von URL herunter und extrahiert Text.

        Args:
            url: URL des PDF-Dokuments

        Returns:
            Dict mit:
                - text: Extrahierter Text
                - pages: Anzahl der Seiten
                - method: Verwendete Extraktionsmethode
                - error: Fehlermeldung falls nicht erfolgreich
                - file_size_mb: Dateigröße in MB
        """
        result = {"text": None, "pages": 0, "method": None, "error": None, "file_size_mb": 0}

        try:
            # PDF herunterladen
            logger.info("pdf_download_started", url=url)
            pdf_content = await self._download_pdf(url)

            if not pdf_content:
                result["error"] = "PDF-Download fehlgeschlagen"
                return result

            # Größe prüfen
            file_size_mb = len(pdf_content) / (1024 * 1024)
            result["file_size_mb"] = round(file_size_mb, 2)

            if file_size_mb > self.max_size_mb:
                result["error"] = f"PDF zu groß: {file_size_mb:.1f}MB (max: {self.max_size_mb}MB)"
                logger.warning("pdf_too_large", size_mb=file_size_mb, url=url)
                return result

            # Text extrahieren
            result = await self._extract_text(pdf_content, result)

            logger.info(
                "pdf_extraction_completed",
                method=result["method"],
                pages=result["pages"],
                text_length=len(result.get("text", "")) if result.get("text") else 0,
            )

        except Exception as e:
            result["error"] = f"Unerwarteter Fehler: {str(e)}"
            logger.error("pdf_extraction_failed", error=str(e), url=url, exc_info=True)

        return result

    async def extract_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        Extrahiert Text aus lokaler PDF-Datei.

        Args:
            file_path: Pfad zur PDF-Datei

        Returns:
            Dict mit extrahierten Daten
        """
        result = {"text": None, "pages": 0, "method": None, "error": None, "file_size_mb": 0}

        try:
            # Dateigröße prüfen
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            result["file_size_mb"] = round(file_size_mb, 2)

            if file_size_mb > self.max_size_mb:
                result["error"] = f"PDF zu groß: {file_size_mb:.1f}MB (max: {self.max_size_mb}MB)"
                return result

            # PDF-Inhalt lesen
            with open(file_path, "rb") as f:
                pdf_content = f.read()

            # Text extrahieren
            result = await self._extract_text(pdf_content, result)

        except Exception as e:
            result["error"] = f"Dateifehler: {str(e)}"
            logger.error("pdf_file_error", error=str(e), file=file_path)

        return result

    async def _download_pdf(self, url: str) -> Optional[bytes]:
        """Lädt PDF von URL herunter mit Timeout und Größenlimit."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # Stream für große Dateien
                async with client.stream("GET", url) as response:
                    response.raise_for_status()

                    # Content-Type prüfen
                    content_type = response.headers.get("content-type", "")
                    if "pdf" not in content_type.lower():
                        logger.warning("not_a_pdf", content_type=content_type, url=url)

                    # Inhalt mit Größenlimit lesen
                    chunks = []
                    total_size = 0
                    max_bytes = self.max_size_mb * 1024 * 1024

                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        total_size += len(chunk)
                        if total_size > max_bytes:
                            logger.warning(
                                "download_size_exceeded",
                                size_mb=total_size / (1024 * 1024),
                                url=url,
                            )
                            return None
                        chunks.append(chunk)

                    return b"".join(chunks)

        except httpx.TimeoutException:
            logger.error("pdf_download_timeout", url=url, timeout=self.timeout_seconds)
        except httpx.HTTPStatusError as e:
            logger.error("pdf_download_http_error", url=url, status=e.response.status_code)
        except Exception as e:
            logger.error("pdf_download_error", url=url, error=str(e))

        return None

    async def _extract_text(self, pdf_content: bytes, result: Dict) -> Dict[str, Any]:
        """
        Versucht Text-Extraktion mit verschiedenen Methoden.

        Reihenfolge:
        1. pdfplumber (beste Qualität)
        2. PyPDF2 (Fallback für problematische PDFs)
        3. pdftotext (System-Tool, falls verfügbar)
        """

        # Methode 1: pdfplumber
        text = await self._extract_with_pdfplumber(pdf_content)
        if text:
            result["text"] = text["text"]
            result["pages"] = text["pages"]
            result["method"] = "pdfplumber"
            return result

        # Methode 2: PyPDF2
        text = await self._extract_with_pypdf2(pdf_content)
        if text:
            result["text"] = text["text"]
            result["pages"] = text["pages"]
            result["method"] = "PyPDF2"
            return result

        # Methode 3: pdftotext (falls installiert)
        text = await self._extract_with_pdftotext(pdf_content)
        if text:
            result["text"] = text["text"]
            result["pages"] = text.get("pages", 0)
            result["method"] = "pdftotext"
            return result

        # Keine Methode erfolgreich
        result["error"] = "Text-Extraktion mit allen Methoden fehlgeschlagen"
        return result

    async def _extract_with_pdfplumber(self, pdf_content: bytes) -> Optional[Dict]:
        """Extrahiert Text mit pdfplumber."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                tmp_path = tmp_file.name

            try:
                with PDF.open(tmp_path) as pdf:
                    # Passwortschutz prüfen
                    if pdf.is_encrypted:
                        logger.warning("pdf_encrypted", method="pdfplumber")
                        return None

                    pages_to_extract = min(len(pdf.pages), self.max_pages)
                    texts = []

                    for i, page in enumerate(pdf.pages[:pages_to_extract]):
                        try:
                            page_text = page.extract_text()
                            if page_text:
                                texts.append(f"--- Seite {i+1} ---\n{page_text}")
                        except Exception as e:
                            logger.warning(
                                "page_extraction_failed",
                                page=i + 1,
                                method="pdfplumber",
                                error=str(e),
                            )

                    if texts:
                        return {"text": "\n\n".join(texts), "pages": len(pdf.pages)}

            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.error("pdfplumber_error", error=str(e))

        return None

    async def _extract_with_pypdf2(self, pdf_content: bytes) -> Optional[Dict]:
        """Fallback: Extrahiert Text mit PyPDF2."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                tmp_path = tmp_file.name

            try:
                reader = PdfReader(tmp_path)

                # Verschlüsselung prüfen
                if reader.is_encrypted:
                    # Versuche mit leerem Passwort
                    if not reader.decrypt(""):
                        logger.warning("pdf_encrypted", method="PyPDF2")
                        return None

                pages_to_extract = min(len(reader.pages), self.max_pages)
                texts = []

                for i in range(pages_to_extract):
                    try:
                        page = reader.pages[i]
                        page_text = page.extract_text()
                        if page_text:
                            texts.append(f"--- Seite {i+1} ---\n{page_text}")
                    except Exception as e:
                        logger.warning(
                            "page_extraction_failed", page=i + 1, method="PyPDF2", error=str(e)
                        )

                if texts:
                    return {"text": "\n\n".join(texts), "pages": len(reader.pages)}

            finally:
                os.unlink(tmp_path)

        except Exception as e:
            logger.error("pypdf2_error", error=str(e))

        return None

    async def _extract_with_pdftotext(self, pdf_content: bytes) -> Optional[Dict]:
        """Fallback: Verwendet System-Tool pdftotext falls verfügbar."""
        try:
            # Prüfe ob pdftotext verfügbar ist
            try:
                subprocess.run(["pdftotext", "-v"], capture_output=True, timeout=1, check=False)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return None

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                tmp_pdf.write(pdf_content)
                tmp_pdf_path = tmp_pdf.name

            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_txt:
                tmp_txt_path = tmp_txt.name

            try:
                # pdftotext mit Layout-Erhaltung
                result = subprocess.run(
                    ["pdftotext", "-layout", "-nopgbrk", tmp_pdf_path, tmp_txt_path],
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    text=True,
                )

                if result.returncode == 0:
                    with open(tmp_txt_path, "r", encoding="utf-8") as f:
                        text = f.read()

                    if text.strip():
                        return {"text": text}
                else:
                    logger.warning(
                        "pdftotext_failed", returncode=result.returncode, stderr=result.stderr
                    )

            finally:
                os.unlink(tmp_pdf_path)
                os.unlink(tmp_txt_path)

        except subprocess.TimeoutExpired:
            logger.error("pdftotext_timeout")
        except Exception as e:
            logger.error("pdftotext_error", error=str(e))

        return None

    def clean_text(self, text: str) -> str:
        """
        Bereinigt extrahierten Text.

        - Entfernt übermäßige Leerzeichen
        - Korrigiert häufige Encoding-Fehler
        - Entfernt Steuerzeichen
        """
        if not text:
            return ""

        # Encoding-Fehler korrigieren (häufig bei deutschen Umlauten)
        replacements = {
            "Ã¼": "ü",
            "Ã¶": "ö",
            "Ã¤": "ä",
            "Ãœ": "Ü",
            "Ã–": "Ö",
            "Ã„": "Ä",
            "ÃŸ": "ß",
            "â€™": "'",
            "â€œ": '"',
            "â€": '"',
            'â€"': "—",
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        # Steuerzeichen entfernen (außer Newline und Tab)
        import re

        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)

        # Mehrfache Leerzeichen/Tabs reduzieren
        text = re.sub(r"[ \t]+", " ", text)

        # Mehrfache Newlines reduzieren (max 2)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def get_text_hash(self, text: str) -> str:
        """Erstellt SHA-256 Hash des Textes für Duplikat-Erkennung."""
        if not text:
            return ""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Convenience-Funktionen für einfache Nutzung
async def extract_pdf_from_url(url: str) -> Dict[str, Any]:
    """Wrapper-Funktion für URL-Extraktion."""
    extractor = PDFExtractor()
    result = await extractor.extract_from_url(url)

    # Text bereinigen falls vorhanden
    if result.get("text"):
        result["text"] = extractor.clean_text(result["text"])
        result["text_hash"] = extractor.get_text_hash(result["text"])

    return result


async def extract_pdf_from_file(file_path: str) -> Dict[str, Any]:
    """Wrapper-Funktion für Datei-Extraktion."""
    extractor = PDFExtractor()
    result = await extractor.extract_from_file(file_path)

    # Text bereinigen falls vorhanden
    if result.get("text"):
        result["text"] = extractor.clean_text(result["text"])
        result["text_hash"] = extractor.get_text_hash(result["text"])

    return result
