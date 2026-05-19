"""
Unit-Tests für den PDF-Extraktor.

Testet alle PDF-Extraktionsmethoden und Edge Cases.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import io

from src.processors.pdf_extractor import PDFExtractor


class TestPDFExtractor:
    """Test-Suite für PDF-Extraktor."""

    @pytest.fixture
    def extractor(self):
        """Erstelle PDFExtractor Instanz."""
        return PDFExtractor()

    @pytest.fixture
    def sample_pdf_content(self):
        """Beispiel PDF-Inhalt."""
        return """URTEIL
        
        Im Namen des Volkes
        
        In der Datenschutzsache
        Max Mustermann ./. Firma GmbH
        
        wegen Verletzung der DSGVO Art. 6 und Art. 15
        
        hat das Landgericht München I durch die 3. Zivilkammer
        am 15. Januar 2024 für Recht erkannt:
        
        Die Beklagte wird verurteilt, die unrechtmäßige
        Datenverarbeitung zu unterlassen."""

    @pytest.mark.asyncio
    async def test_pdfplumber_extraction_success(self, extractor, sample_pdf_content, tmp_path):
        """Test erfolgreiche Extraktion mit pdfplumber."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nDummy PDF content")

        with patch("pdfplumber.open") as mock_pdf:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = sample_pdf_content
            mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

            result = await extractor.extract_text(str(pdf_path))

            assert result["success"] is True
            assert result["method"] == "pdfplumber"
            assert "DSGVO Art. 6" in result["text"]
            assert result["pages"] == 1
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_pypdf2_fallback(self, extractor, sample_pdf_content, tmp_path):
        """Test Fallback zu PyPDF2 wenn pdfplumber fehlschlägt."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nDummy PDF content")

        # pdfplumber schlägt fehl
        with patch("pdfplumber.open") as mock_pdfplumber:
            mock_pdfplumber.side_effect = Exception("pdfplumber failed")

            # PyPDF2 funktioniert
            with patch("PyPDF2.PdfReader") as mock_pypdf:
                mock_reader = MagicMock()
                mock_page = MagicMock()
                mock_page.extract_text.return_value = sample_pdf_content
                mock_reader.pages = [mock_page]
                mock_pypdf.return_value = mock_reader

                with patch("builtins.open", mock_open(read_data=b"PDF content")):
                    result = await extractor.extract_text(str(pdf_path))

                assert result["success"] is True
                assert result["method"] == "pypdf2"
                assert "DSGVO Art. 6" in result["text"]

    @pytest.mark.asyncio
    async def test_pdftotext_fallback(self, extractor, sample_pdf_content, tmp_path):
        """Test Fallback zu pdftotext wenn beide Python-Methoden fehlschlagen."""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nDummy PDF content")

        # Beide Python-Methoden schlagen fehl
        with patch("pdfplumber.open") as mock_pdfplumber:
            mock_pdfplumber.side_effect = Exception("pdfplumber failed")

            with patch("PyPDF2.PdfReader") as mock_pypdf:
                mock_pypdf.side_effect = Exception("PyPDF2 failed")

                # pdftotext funktioniert
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout=sample_pdf_content, stderr="", returncode=0
                    )

                    result = await extractor.extract_text(str(pdf_path))

                    assert result["success"] is True
                    assert result["method"] == "pdftotext"
                    assert "DSGVO Art. 6" in result["text"]

    @pytest.mark.asyncio
    async def test_password_protected_pdf(self, extractor, tmp_path):
        """Test Verarbeitung von passwortgeschützten PDFs."""
        pdf_path = tmp_path / "protected.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nProtected")

        with patch("pdfplumber.open") as mock_pdf:
            mock_pdf.side_effect = Exception("PDF is encrypted")

            with patch("PyPDF2.PdfReader") as mock_pypdf:
                mock_pypdf.side_effect = Exception("PDF is encrypted")

                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = Exception("Password required")

                    result = await extractor.extract_text(str(pdf_path))

                    assert result["success"] is False
                    assert (
                        "encrypted" in result["error"].lower()
                        or "password" in result["error"].lower()
                    )

    @pytest.mark.asyncio
    async def test_size_limit_enforcement(self, extractor, tmp_path):
        """Test dass zu große PDFs abgelehnt werden."""
        pdf_path = tmp_path / "large.pdf"
        # Erstelle eine Datei > 10MB
        large_content = b"x" * (11 * 1024 * 1024)
        pdf_path.write_bytes(large_content)

        result = await extractor.extract_text(str(pdf_path))

        assert result["success"] is False
        assert "size limit" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_encoding_correction(self, extractor, tmp_path):
        """Test automatische Encoding-Korrektur."""
        pdf_path = tmp_path / "encoding.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nTest")

        # Text mit falscher Kodierung
        broken_text = "Test mit Ã¤Ã¶Ã¼ Umlauten"
        expected_text = "Test mit äöü Umlauten"

        with patch("pdfplumber.open") as mock_pdf:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = broken_text
            mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

            # Mock die Encoding-Korrektur
            with patch.object(extractor, "_fix_encoding", return_value=expected_text):
                result = await extractor.extract_text(str(pdf_path))

                assert result["success"] is True
                assert result["text"] == expected_text

    @pytest.mark.asyncio
    async def test_empty_pdf(self, extractor, tmp_path):
        """Test Verarbeitung von PDFs ohne Text."""
        pdf_path = tmp_path / "empty.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        with patch("pdfplumber.open") as mock_pdf:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = ""
            mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

            result = await extractor.extract_text(str(pdf_path))

            assert result["success"] is True
            assert result["text"] == ""
            assert result["pages"] == 1

    @pytest.mark.asyncio
    async def test_multipage_pdf(self, extractor, tmp_path):
        """Test Verarbeitung von mehrseitigen PDFs."""
        pdf_path = tmp_path / "multipage.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nMultipage")

        page_contents = [
            "Seite 1: Einleitung",
            "Seite 2: Hauptteil mit Art. 6 DSGVO",
            "Seite 3: Schluss",
        ]

        with patch("pdfplumber.open") as mock_pdf:
            mock_pages = []
            for content in page_contents:
                mock_page = MagicMock()
                mock_page.extract_text.return_value = content
                mock_pages.append(mock_page)

            mock_pdf.return_value.__enter__.return_value.pages = mock_pages

            result = await extractor.extract_text(str(pdf_path))

            assert result["success"] is True
            assert result["pages"] == 3
            assert all(f"Seite {i+1}" in result["text"] for i in range(3))
            assert "Art. 6 DSGVO" in result["text"]

    @pytest.mark.asyncio
    async def test_corrupted_pdf(self, extractor, tmp_path):
        """Test Verarbeitung von korrupten PDFs."""
        pdf_path = tmp_path / "corrupted.pdf"
        pdf_path.write_bytes(b"Not a valid PDF file")

        with patch("pdfplumber.open") as mock_pdfplumber:
            mock_pdfplumber.side_effect = Exception("Invalid PDF")

            with patch("PyPDF2.PdfReader") as mock_pypdf:
                mock_pypdf.side_effect = Exception("Invalid PDF")

                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = Exception("Not a PDF file")

                    result = await extractor.extract_text(str(pdf_path))

                    assert result["success"] is False
                    assert "error" in result
                    assert result["method"] is None

    @pytest.mark.asyncio
    async def test_file_not_found(self, extractor):
        """Test Verarbeitung wenn PDF-Datei nicht existiert."""
        result = await extractor.extract_text("/non/existent/file.pdf")

        assert result["success"] is False
        assert "not found" in result["error"].lower() or "exist" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_special_characters_in_path(self, extractor, tmp_path):
        """Test Verarbeitung von Dateipfaden mit Sonderzeichen."""
        pdf_path = tmp_path / "test äöü €.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nTest")

        with patch("pdfplumber.open") as mock_pdf:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Test content"
            mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

            result = await extractor.extract_text(str(pdf_path))

            assert result["success"] is True
            assert result["text"] == "Test content"

    @pytest.mark.asyncio
    async def test_timeout_handling(self, extractor, tmp_path):
        """Test Timeout-Handling bei langsamer Extraktion."""
        pdf_path = tmp_path / "slow.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nSlow")

        import asyncio

        with patch("pdfplumber.open") as mock_pdf:

            async def slow_extract():
                await asyncio.sleep(100)  # Simuliere sehr langsame Extraktion
                return "Text"

            mock_page = MagicMock()
            mock_page.extract_text = slow_extract
            mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

            # Timeout sollte greifen
            with patch("src.processors.pdf_extractor.PDF_TIMEOUT_SECONDS", 0.1):
                result = await extractor.extract_text(str(pdf_path))

                # Je nach Implementierung könnte es fehlschlagen oder zur nächsten Methode wechseln
                assert "timeout" in str(result).lower() or result["method"] != "pdfplumber"

    def test_clean_text(self, extractor):
        """Test Text-Bereinigung."""
        dirty_text = "  Test  \n\n\n  mit   vielen    Leerzeichen  \t\r\n  "
        clean = extractor._clean_text(dirty_text)

        assert clean == "Test mit vielen Leerzeichen"

        # Test mit None
        assert extractor._clean_text(None) == ""

        # Test mit leerem String
        assert extractor._clean_text("") == ""

        # Test mit nur Whitespace
        assert extractor._clean_text("   \n\t\r  ") == ""

    def test_fix_encoding(self, extractor):
        """Test Encoding-Fixes."""
        # Test UTF-8 Mojibake
        broken = "MÃ¼nchen"
        fixed = extractor._fix_encoding(broken)
        assert fixed == "München"

        # Test bereits korrekter Text
        correct = "München"
        assert extractor._fix_encoding(correct) == correct

        # Test mit None
        assert extractor._fix_encoding(None) == ""

    @pytest.mark.asyncio
    async def test_extract_from_url(self, extractor):
        """Test PDF-Download und Extraktion von URL."""
        test_url = "https://example.com/test.pdf"
        sample_content = "Downloaded PDF content"

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"%PDF-1.4\nTest"
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_file = MagicMock()
                mock_file.name = "/tmp/test.pdf"
                mock_temp.return_value.__enter__.return_value = mock_file

                with patch("pdfplumber.open") as mock_pdf:
                    mock_page = MagicMock()
                    mock_page.extract_text.return_value = sample_content
                    mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

                    result = await extractor.extract_from_url(test_url)

                    assert result["success"] is True
                    assert result["text"] == sample_content
                    mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_extraction(self, extractor, tmp_path):
        """Test Batch-Extraktion mehrerer PDFs."""
        # Erstelle mehrere Test-PDFs
        pdf_paths = []
        for i in range(3):
            pdf_path = tmp_path / f"test_{i}.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nTest")
            pdf_paths.append(str(pdf_path))

        with patch("pdfplumber.open") as mock_pdf:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Test content"
            mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

            results = []
            for path in pdf_paths:
                result = await extractor.extract_text(path)
                results.append(result)

            assert len(results) == 3
            assert all(r["success"] for r in results)
            assert all(r["text"] == "Test content" for r in results)
