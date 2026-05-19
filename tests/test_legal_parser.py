"""
Unit-Tests für den Legal Parser.

Testet die Extraktion deutscher Rechtsstrukturen aus Gerichtsentscheidungen.
"""

import pytest
from datetime import date

from src.processors.legal_parser import LegalParser


class TestLegalParser:
    """Test-Suite für Legal Parser."""

    @pytest.fixture
    def parser(self):
        """Erstelle LegalParser Instanz."""
        return LegalParser()

    @pytest.fixture
    def sample_urteil(self):
        """Beispiel-Urteil mit vollständiger Struktur."""
        return """
        URTEIL
        
        Im Namen des Volkes
        
        In dem Rechtsstreit
        
        Max Mustermann, Musterstraße 1, 80333 München
        - Kläger -
        
        gegen
        
        Firma GmbH, vertreten durch die Geschäftsführer,
        Businessstraße 10, 80331 München
        - Beklagte -
        
        wegen Datenschutzverletzung
        
        hat das Landgericht München I durch die 3. Zivilkammer unter Vorsitz von
        Richterin Dr. Schmidt und die Richter Müller und Meyer nach mündlicher
        Verhandlung vom 15. Januar 2024
        
        für Recht erkannt:
        
        LEITSATZ:
        Die Verarbeitung personenbezogener Daten ohne ausreichende Rechtsgrundlage
        nach Art. 6 DSGVO stellt eine unzulässige Datenverarbeitung dar. Der Betroffene
        hat Anspruch auf Unterlassung und Schadensersatz nach Art. 82 DSGVO.
        
        TENOR:
        1. Die Beklagte wird verurteilt, es zu unterlassen, personenbezogene Daten
           des Klägers ohne dessen Einwilligung zu verarbeiten.
        
        2. Die Beklagte wird verurteilt, an den Kläger 5.000 EUR nebst Zinsen in
           Höhe von 5 Prozentpunkten über dem Basiszinssatz seit Rechtshängigkeit
           zu zahlen.
        
        3. Die Beklagte trägt die Kosten des Rechtsstreits.
        
        4. Das Urteil ist vorläufig vollstreckbar.
        
        TATBESTAND:
        Der Kläger begehrt Unterlassung der Datenverarbeitung und Schadensersatz.
        
        Der Kläger ist Kunde der Beklagten seit 2020. Im März 2023 stellte er fest,
        dass die Beklagte seine personenbezogenen Daten einschließlich besonderer
        Kategorien personenbezogener Daten nach Art. 9 DSGVO an Dritte weitergegeben
        hatte, ohne hierfür eine Einwilligung eingeholt zu haben.
        
        Der Kläger beantragt,
        die Beklagte zu verurteilen wie geschehen.
        
        Die Beklagte beantragt,
        die Klage abzuweisen.
        
        Sie behauptet, die Datenverarbeitung sei auf Grundlage eines berechtigten
        Interesses nach Art. 6 Abs. 1 lit. f DSGVO erfolgt.
        
        ENTSCHEIDUNGSGRÜNDE:
        Die zulässige Klage ist begründet.
        
        I. Der Kläger hat gegen die Beklagte einen Anspruch auf Unterlassung der
        Datenverarbeitung aus Art. 21 DSGVO.
        
        Die Beklagte hat personenbezogene Daten des Klägers ohne ausreichende
        Rechtsgrundlage verarbeitet. Ein berechtigtes Interesse der Beklagten
        liegt nicht vor, da die Interessen und Grundrechte des Klägers überwiegen.
        
        II. Der Schadensersatzanspruch ergibt sich aus Art. 82 DSGVO.
        
        Dem Kläger ist durch die unrechtmäßige Datenverarbeitung ein immaterieller
        Schaden entstanden. Die Höhe von 5.000 EUR ist angemessen.
        
        III. Die Kostenentscheidung folgt aus § 91 ZPO.
        
        IV. Die Entscheidung über die vorläufige Vollstreckbarkeit beruht auf
        § 709 ZPO.
        
        RECHTSMITTELBELEHRUNG:
        Gegen dieses Urteil kann Berufung eingelegt werden.
        """

    @pytest.mark.asyncio
    async def test_extract_leitsatz(self, parser, sample_urteil):
        """Test Extraktion des Leitsatzes."""
        result = await parser.parse_german_legal_structure(sample_urteil)

        assert result["leitsatz"] is not None
        assert "Art. 6 DSGVO" in result["leitsatz"]
        assert "unzulässige Datenverarbeitung" in result["leitsatz"]
        assert "Art. 82 DSGVO" in result["leitsatz"]

    @pytest.mark.asyncio
    async def test_extract_tenor(self, parser, sample_urteil):
        """Test Extraktion des Tenors."""
        result = await parser.parse_german_legal_structure(sample_urteil)

        assert result["tenor"] is not None
        assert "unterlassen" in result["tenor"].lower()
        assert "5.000 EUR" in result["tenor"]
        assert "vorläufig vollstreckbar" in result["tenor"].lower()

    @pytest.mark.asyncio
    async def test_extract_tatbestand(self, parser, sample_urteil):
        """Test Extraktion des Tatbestands."""
        result = await parser.parse_german_legal_structure(sample_urteil)

        assert result["tatbestand"] is not None
        assert "Der Kläger begehrt" in result["tatbestand"]
        assert "März 2023" in result["tatbestand"]
        assert "Art. 9 DSGVO" in result["tatbestand"]
        assert "beantragt" in result["tatbestand"].lower()

    @pytest.mark.asyncio
    async def test_extract_entscheidungsgruende(self, parser, sample_urteil):
        """Test Extraktion der Entscheidungsgründe."""
        result = await parser.parse_german_legal_structure(sample_urteil)

        assert result["entscheidungsgruende"] is not None
        assert "Die zulässige Klage ist begründet" in result["entscheidungsgruende"]
        assert "Art. 21 DSGVO" in result["entscheidungsgruende"]
        assert "Art. 82 DSGVO" in result["entscheidungsgruende"]
        assert "§ 91 ZPO" in result["entscheidungsgruende"]

    @pytest.mark.asyncio
    async def test_extract_metadata(self, parser, sample_urteil):
        """Test Extraktion von Metadaten."""
        result = await parser.parse_german_legal_structure(sample_urteil)

        metadata = result.get("metadata", {})
        assert metadata is not None
        assert metadata.get("gericht") == "Landgericht München I"
        assert metadata.get("kammer") == "3. Zivilkammer"
        assert "15. Januar 2024" in str(metadata.get("verhandlungsdatum", ""))

    @pytest.mark.asyncio
    async def test_rechtskraft_detection(self, parser):
        """Test Erkennung des Rechtskraft-Status."""
        # Rechtskräftig
        text_rechtskraeftig = "Das Urteil ist rechtskräftig seit dem 01.02.2024."
        result = await parser.parse_german_legal_structure(text_rechtskraeftig)
        assert result["rechtskraft_status"] == "rechtskräftig"
        assert result["rechtskraft_datum"] == date(2024, 2, 1)

        # Berufung möglich
        text_berufung = "Gegen dieses Urteil kann Berufung eingelegt werden."
        result = await parser.parse_german_legal_structure(text_berufung)
        assert result["rechtskraft_status"] == "berufung_möglich"

        # Berufung eingelegt
        text_berufung_eingelegt = "Die Beklagte hat Berufung eingelegt."
        result = await parser.parse_german_legal_structure(text_berufung_eingelegt)
        assert result["rechtskraft_status"] == "berufung_eingelegt"

        # Aufgehoben
        text_aufgehoben = "Das Urteil wurde durch den BGH aufgehoben."
        result = await parser.parse_german_legal_structure(text_aufgehoben)
        assert result["rechtskraft_status"] == "aufgehoben"

    @pytest.mark.asyncio
    async def test_alternative_section_markers(self, parser):
        """Test alternative Bezeichnungen für Abschnitte."""
        text_alternative = """
        Orientierungssatz:
        Die DSGVO ist anwendbar.
        
        Urteilsformel:
        Die Klage wird abgewiesen.
        
        Sachverhalt:
        Der Kläger wendet sich gegen die Datenverarbeitung.
        
        Gründe:
        Die Klage ist unbegründet.
        """

        result = await parser.parse_german_legal_structure(text_alternative)

        assert "DSGVO ist anwendbar" in result["leitsatz"]
        assert "Klage wird abgewiesen" in result["tenor"]
        assert "wendet sich gegen" in result["tatbestand"]
        assert "unbegründet" in result["entscheidungsgruende"]

    @pytest.mark.asyncio
    async def test_empty_text(self, parser):
        """Test Verarbeitung von leerem Text."""
        result = await parser.parse_german_legal_structure("")

        assert result["leitsatz"] is None
        assert result["tenor"] is None
        assert result["tatbestand"] is None
        assert result["entscheidungsgruende"] is None
        assert result["rechtskraft_status"] == "unbekannt"

    @pytest.mark.asyncio
    async def test_partial_structure(self, parser):
        """Test Verarbeitung von Texten mit nur teilweiser Struktur."""
        text_partial = """
        TENOR:
        Die Klage wird abgewiesen.
        
        Die Kosten trägt der Kläger.
        
        Weitere Informationen ohne klare Struktur.
        """

        result = await parser.parse_german_legal_structure(text_partial)

        assert result["tenor"] is not None
        assert "Klage wird abgewiesen" in result["tenor"]
        assert result["leitsatz"] is None  # Nicht vorhanden
        assert result["tatbestand"] is None  # Nicht vorhanden

    @pytest.mark.asyncio
    async def test_beschluss_format(self, parser):
        """Test Verarbeitung von Beschlüssen statt Urteilen."""
        text_beschluss = """
        BESCHLUSS
        
        In der Verwaltungsstreitsache
        
        hat das Verwaltungsgericht München beschlossen:
        
        Der Antrag auf Erlass einer einstweiligen Anordnung wird abgelehnt.
        
        GRÜNDE:
        Der Antrag ist unbegründet. Der Antragsteller hat keinen Anordnungsanspruch
        glaubhaft gemacht.
        """

        result = await parser.parse_german_legal_structure(text_beschluss)

        assert "einstweiligen Anordnung wird abgelehnt" in (result["tenor"] or "")
        assert "unbegründet" in (result["entscheidungsgruende"] or "")

    @pytest.mark.asyncio
    async def test_verfuegung_format(self, parser):
        """Test Verarbeitung von Verfügungen."""
        text_verfuegung = """
        VERFÜGUNG
        
        Die Datenschutzbehörde verfügt:
        
        1. Die Firma GmbH wird verpflichtet, die unrechtmäßige Datenverarbeitung
           einzustellen.
        
        2. Es wird ein Bußgeld in Höhe von 50.000 EUR festgesetzt.
        
        BEGRÜNDUNG:
        Die Firma hat gegen Art. 5, 6 und 32 DSGVO verstoßen.
        """

        result = await parser.parse_german_legal_structure(text_verfuegung)

        assert "verpflichtet" in (result["tenor"] or "")
        assert "50.000 EUR" in (result["tenor"] or "")
        assert "Art. 5, 6 und 32 DSGVO" in (result["entscheidungsgruende"] or "")

    @pytest.mark.asyncio
    async def test_extract_case_number(self, parser):
        """Test Extraktion von Aktenzeichen."""
        texts_with_az = [
            "Az.: 3 O 123/23",
            "Aktenzeichen: 11 U 456/24",
            "Az: VG-7-K-789/22",
            "Geschäftsnummer: 1 BvR 111/21",
        ]

        for text in texts_with_az:
            result = await parser.parse_german_legal_structure(text)
            metadata = result.get("metadata", {})
            assert metadata.get("aktenzeichen") is not None

    @pytest.mark.asyncio
    async def test_extract_parties(self, parser):
        """Test Extraktion der Parteien."""
        text_with_parties = """
        Kläger: Max Mustermann, vertreten durch RA Dr. Schmidt
        Beklagter: Firma GmbH, gesetzlich vertreten durch GF Müller
        """

        result = await parser.parse_german_legal_structure(text_with_parties)
        metadata = result.get("metadata", {})

        assert "Max Mustermann" in metadata.get("klaeger", "")
        assert "Firma GmbH" in metadata.get("beklagter", "")

    @pytest.mark.asyncio
    async def test_normalize_whitespace(self, parser):
        """Test Normalisierung von Whitespace."""
        text_with_spaces = """
        TENOR:
        
        
        Die    Klage     wird
        
        
        abgewiesen.
        """

        result = await parser.parse_german_legal_structure(text_with_spaces)

        # Sollte normalisiert sein
        assert result["tenor"] is not None
        assert "  " not in result["tenor"]  # Keine doppelten Leerzeichen
        assert "\n\n\n" not in result["tenor"]  # Keine mehrfachen Zeilenumbrüche

    @pytest.mark.asyncio
    async def test_complex_date_formats(self, parser):
        """Test verschiedene Datumsformate."""
        date_formats = [
            ("rechtskräftig seit 01.02.2024", date(2024, 2, 1)),
            ("rechtskräftig seit dem 1. Februar 2024", date(2024, 2, 1)),
            ("Rechtskraft: 01/02/2024", date(2024, 2, 1)),
            ("rechtskräftig ab 2024-02-01", date(2024, 2, 1)),
        ]

        for text, expected_date in date_formats:
            result = await parser.parse_german_legal_structure(text)
            assert result["rechtskraft_datum"] == expected_date

    @pytest.mark.asyncio
    async def test_multiple_dsgvo_references(self, parser):
        """Test Extraktion mehrerer DSGVO-Referenzen."""
        text = """
        Die Beklagte hat gegen Art. 5 Abs. 1 lit. a, Art. 6 Abs. 1,
        Art. 13, Art. 14, Art. 15 bis 22 und Art. 32 DSGVO verstoßen.
        """

        result = await parser.parse_german_legal_structure(text)

        # Parser sollte alle Artikel erkennen
        full_text = str(result)
        assert "Art. 5" in full_text
        assert "Art. 6" in full_text
        assert "Art. 32" in full_text

    @pytest.mark.asyncio
    async def test_english_text_handling(self, parser):
        """Test Verarbeitung von englischem Text."""
        english_text = """
        JUDGMENT
        
        The court decides:
        1. The defendant shall cease processing personal data.
        
        REASONS:
        The defendant violated GDPR Article 6.
        """

        result = await parser.parse_german_legal_structure(english_text)

        # Sollte trotzdem versuchen, Struktur zu erkennen
        # Auch wenn es englisch ist
        assert result is not None
        # Aber deutsche Marker werden nicht gefunden
        assert result["leitsatz"] is None
        assert result["tenor"] is None
