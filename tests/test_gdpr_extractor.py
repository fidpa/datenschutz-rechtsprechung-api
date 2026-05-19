"""
Tests für den DSGVO-Artikel-Extraktor.
"""

import pytest
from src.analyzers.gdpr_extractor import GDPRArticleExtractor, ArticleReference


class TestGDPRArticleExtractor:
    """Test-Suite für DSGVO-Artikel-Extraktion."""

    @pytest.fixture
    def extractor(self):
        """Erstellt Extraktor-Instanz."""
        return GDPRArticleExtractor()

    def test_extract_simple_gdpr_articles(self, extractor):
        """Test der Extraktion einfacher DSGVO-Artikel."""
        text = """
        Die Verarbeitung personenbezogener Daten nach Art. 6 DSGVO 
        ist nur rechtmäßig, wenn eine Rechtsgrundlage vorliegt. 
        Besondere Kategorien nach Art. 9 DSGVO bedürfen zusätzlicher Rechtfertigung.
        """

        articles = extractor.extract_gdpr_articles(text)

        assert "Art. 6 DSGVO" in articles
        assert "Art. 9 DSGVO" in articles
        assert len(articles) == 2

    def test_extract_gdpr_with_paragraph(self, extractor):
        """Test der Extraktion mit Absätzen."""
        text = """
        Die Rechtsgrundlage ergibt sich aus Art. 6 Abs. 1 DSGVO.
        Zudem ist Art. 13 Abs. 2 DSGVO zu beachten.
        """

        articles = extractor.extract_gdpr_articles(text)

        assert "Art. 6 Abs. 1 DSGVO" in articles
        assert "Art. 13 Abs. 2 DSGVO" in articles
        assert len(articles) == 2

    def test_extract_gdpr_with_letter(self, extractor):
        """Test der Extraktion mit Buchstaben (lit.)."""
        text = "Die Einwilligung nach Art. 6 Abs. 1 lit. a DSGVO muss freiwillig sein."

        articles = extractor.extract_gdpr_articles(text)

        assert "Art. 6 Abs. 1 lit. a DSGVO" in articles

    def test_extract_different_formats(self, extractor):
        """Test verschiedener Schreibweisen."""
        text = """
        Artikel 7 DSGVO regelt die Einwilligung.
        Art. 12 DS-GVO betrifft transparente Information.
        Article 15 GDPR provides access rights.
        Art. 16(1) DSGVO ermöglicht Berichtigung.
        """

        articles = extractor.extract_gdpr_articles(text)

        assert "Art. 7 DSGVO" in articles
        assert "Art. 12 DSGVO" in articles
        assert "Art. 15 DSGVO" in articles
        assert "Art. 16 Abs. 1 DSGVO" in articles

    def test_extract_bdsg_sections(self, extractor):
        """Test der BDSG-Paragraphen-Extraktion."""
        text = "Gemäß § 26 BDSG ist die Datenverarbeitung im Beschäftigungsverhältnis geregelt."

        sections = extractor.extract_bdsg_sections(text)

        assert "§ 26 BDSG" in sections
        assert len(sections) == 1

    def test_extract_bdsg_range(self, extractor):
        """Test der BDSG-Bereichs-Extraktion."""
        text = "Die §§ 26 bis 28 BDSG regeln den Beschäftigtendatenschutz."

        sections = extractor.extract_bdsg_sections(text)

        assert "§ 26 BDSG" in sections
        assert "§ 27 BDSG" in sections
        assert "§ 28 BDSG" in sections
        assert len(sections) == 3

    def test_extract_bdsg_with_paragraph(self, extractor):
        """Test BDSG mit Absatz."""
        text = "Nach § 85 Abs. 2 BDSG können Bußgelder verhängt werden."

        sections = extractor.extract_bdsg_sections(text)

        assert "§ 85 Abs. 2 BDSG" in sections

    def test_extract_keywords(self, extractor):
        """Test der Keyword-Extraktion."""
        text = """
        Die Einwilligung des Betroffenen zur Verarbeitung personenbezogener Daten
        muss freiwillig erfolgen. Der Verantwortliche muss eine Rechtsgrundlage nachweisen.
        Bei einem Datenschutzverstoß droht ein Bußgeld.
        """

        keywords = extractor.extract_keywords(text)

        assert "Einwilligung" in keywords
        assert "Verarbeitung" in keywords
        assert "personenbezogener Daten" in keywords or "personenbezogene Daten" in keywords
        assert "Betroffenen" in keywords or "Betroffene" in keywords
        assert "Verantwortliche" in keywords or "Verantwortlichen" in keywords
        assert "Rechtsgrundlage" in keywords
        assert "Datenschutzverstoß" in keywords
        assert "Bußgeld" in keywords

    def test_no_duplicates(self, extractor):
        """Test dass keine Duplikate zurückgegeben werden."""
        text = """
        Art. 6 DSGVO wird mehrfach erwähnt. Art. 6 DSGVO ist wichtig.
        Nochmal Art. 6 DSGVO für gutes Maß.
        """

        articles = extractor.extract_gdpr_articles(text)

        assert articles.count("Art. 6 DSGVO") == 1
        assert len(articles) == 1

    def test_complex_legal_text(self, extractor):
        """Test mit komplexem rechtlichen Text."""
        text = """
        Das Gericht stützt seine Entscheidung auf Art. 6 Abs. 1 lit. f DSGVO
        i.V.m. Art. 13 DSGVO. Die Informationspflichten nach Art. 13 Abs. 1 und 
        Abs. 2 DSGVO wurden nicht erfüllt. Zudem liegt ein Verstoß gegen 
        Art. 32 DSGVO (technische und organisatorische Maßnahmen) vor.
        
        Im deutschen Recht ist zusätzlich § 26 Abs. 1 BDSG zu beachten,
        der spezielle Regelungen für Beschäftigtendaten enthält.
        Die §§ 83 bis 84 BDSG regeln die Aufsichtsbehörden.
        """

        gdpr_articles, bdsg_sections = extractor.extract_all(text)

        # DSGVO Artikel
        assert "Art. 6 Abs. 1 lit. f DSGVO" in gdpr_articles
        assert "Art. 13 DSGVO" in gdpr_articles
        assert "Art. 13 Abs. 1 DSGVO" in gdpr_articles
        assert "Art. 13 Abs. 2 DSGVO" in gdpr_articles
        assert "Art. 32 DSGVO" in gdpr_articles

        # BDSG Paragraphen
        assert "§ 26 Abs. 1 BDSG" in bdsg_sections
        assert "§ 83 BDSG" in bdsg_sections
        assert "§ 84 BDSG" in bdsg_sections

    def test_article_reference_class(self):
        """Test der ArticleReference Datenklasse."""
        ref1 = ArticleReference(article="6", paragraph="1", subparagraph="a", law="DSGVO")
        assert str(ref1) == "Art. 6 Abs. 1 lit. a DSGVO"

        ref2 = ArticleReference(article="13", law="DSGVO")
        assert str(ref2) == "Art. 13 DSGVO"

        ref3 = ArticleReference(article="26", paragraph="1", law="BDSG")
        assert str(ref3) == "§ 26 Abs. 1 BDSG"

        # Test Gleichheit
        ref4 = ArticleReference(article="6", paragraph="1", subparagraph="a", law="DSGVO")
        assert ref1 == ref4
        assert hash(ref1) == hash(ref4)

    def test_statistics(self, extractor):
        """Test der Statistik-Funktionalität."""
        text1 = "Art. 6 DSGVO und § 26 BDSG sind relevant."
        text2 = "Art. 13 DSGVO regelt Informationspflichten."

        extractor.extract_all(text1)
        extractor.extract_all(text2)

        stats = extractor.get_statistics()

        assert stats["total_processed"] == 2
        assert stats["dsr_articles_found"] == 2  # Art. 6 und Art. 13
        assert stats["bdsg_sections_found"] == 1  # § 26

    def test_empty_text(self, extractor):
        """Test mit leerem Text."""
        articles = extractor.extract_gdpr_articles("")
        sections = extractor.extract_bdsg_sections("")

        assert articles == []
        assert sections == []

    def test_no_matches(self, extractor):
        """Test mit Text ohne rechtliche Referenzen."""
        text = "Dies ist ein Text ohne jegliche Gesetzesverweise."

        articles = extractor.extract_gdpr_articles(text)
        sections = extractor.extract_bdsg_sections(text)

        assert articles == []
        assert sections == []
