"""
Tests für den deutschen Rechtstext-Anonymisierer.
"""

import pytest
from unittest.mock import Mock, MagicMock
import spacy
from spacy.tokens import Doc, Span

from src.processors.anonymizer import GermanLegalAnonymizer, AnonymizationResult


class TestGermanLegalAnonymizer:
    """Test-Suite für den Anonymisierer."""

    @pytest.fixture
    def mock_nlp(self):
        """Erstellt ein Mock spaCy-Modell für Tests."""
        nlp = Mock()
        return nlp

    @pytest.fixture
    def anonymizer_with_mock(self, mock_nlp):
        """Erstellt Anonymisierer mit Mock-NLP."""
        return GermanLegalAnonymizer(nlp=mock_nlp)

    def create_mock_doc(self, nlp, text, entities):
        """
        Erstellt ein Mock Doc-Objekt mit Entitäten.

        Args:
            nlp: Mock NLP Objekt
            text: Der Text
            entities: Liste von (text, label, start_char, end_char) Tupeln
        """
        doc = Mock(spec=Doc)
        doc.text = text

        # Erstelle Mock-Entitäten
        mock_ents = []
        for ent_text, label, start, end in entities:
            ent = Mock(spec=Span)
            ent.text = ent_text
            ent.label_ = label
            ent.start_char = start
            ent.end_char = end
            mock_ents.append(ent)

        doc.ents = mock_ents
        return doc

    def test_anonymize_person_names(self, anonymizer_with_mock):
        """Test der Personennamen-Anonymisierung."""
        text = "Max Mustermann hat eine Beschwerde eingereicht."

        # Mock das NLP-Ergebnis
        doc = self.create_mock_doc(
            anonymizer_with_mock.nlp, text, [("Max Mustermann", "PER", 0, 14)]
        )
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text)

        assert "[Person 1]" in result.anonymized_text
        assert "Max Mustermann" not in result.anonymized_text
        assert len(result.mappings) == 1
        assert result.entity_types["[Person 1]"] == "PERSON"

    def test_preserve_legal_roles(self, anonymizer_with_mock):
        """Test dass Rechtsrollen erhalten bleiben."""
        text = "Der Kläger Max Mustermann verklagt die Beklagte Erika Musterfrau."

        doc = self.create_mock_doc(
            anonymizer_with_mock.nlp,
            text,
            [("Kläger Max Mustermann", "PER", 4, 25), ("Beklagte Erika Musterfrau", "PER", 40, 65)],
        )
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text)

        # Rechtsrollen sollten erhalten bleiben
        assert "Kläger" in result.anonymized_text
        assert "Beklagte" in result.anonymized_text

        # Namen sollten nicht anonymisiert werden (Teil der Rechtsrolle)
        assert result.anonymized_text == text  # Keine Änderung

    def test_preserve_court_abbreviations(self, anonymizer_with_mock):
        """Test dass Gerichtsabkürzungen erhalten bleiben."""
        text = "Das OLG München hat entschieden."

        doc = self.create_mock_doc(anonymizer_with_mock.nlp, text, [("OLG München", "ORG", 4, 15)])
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text)

        # Gericht sollte erhalten bleiben
        assert "OLG" in result.anonymized_text
        assert result.anonymized_text == text

    def test_anonymize_organizations(self, anonymizer_with_mock):
        """Test der Organisations-Anonymisierung."""
        text = "Die Firma ABC GmbH wurde verklagt."

        doc = self.create_mock_doc(anonymizer_with_mock.nlp, text, [("ABC GmbH", "ORG", 10, 18)])
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text, anonymize_orgs=True)

        assert "[Organisation 1]" in result.anonymized_text
        assert "ABC GmbH" not in result.anonymized_text
        assert result.entity_types["[Organisation 1]"] == "ORGANIZATION"

    def test_skip_organization_anonymization(self, anonymizer_with_mock):
        """Test dass Organisationen optional nicht anonymisiert werden."""
        text = "Die Firma ABC GmbH wurde verklagt."

        doc = self.create_mock_doc(anonymizer_with_mock.nlp, text, [("ABC GmbH", "ORG", 10, 18)])
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text, anonymize_orgs=False)

        assert "ABC GmbH" in result.anonymized_text
        assert "[Organisation" not in result.anonymized_text

    def test_anonymize_locations(self, anonymizer_with_mock):
        """Test der Orts-Anonymisierung."""
        text = "Der Vorfall ereignete sich in Kleinstadt."

        doc = self.create_mock_doc(anonymizer_with_mock.nlp, text, [("Kleinstadt", "LOC", 31, 41)])
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text, anonymize_locations=True)

        assert "[Ort 1]" in result.anonymized_text
        assert "Kleinstadt" not in result.anonymized_text
        assert result.entity_types["[Ort 1]"] == "LOCATION"

    def test_consistent_name_replacement(self, anonymizer_with_mock):
        """Test dass gleiche Namen konsistent ersetzt werden."""
        text = "Max Mustermann sagte aus. Später bestätigte Max Mustermann seine Aussage."

        doc = self.create_mock_doc(
            anonymizer_with_mock.nlp,
            text,
            [("Max Mustermann", "PER", 0, 14), ("Max Mustermann", "PER", 45, 59)],
        )
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text)

        # Beide Vorkommen sollten durch denselben Platzhalter ersetzt werden
        assert result.anonymized_text.count("[Person 1]") == 2
        assert "Max Mustermann" not in result.anonymized_text

    def test_preserve_legal_references(self, anonymizer_with_mock):
        """Test dass rechtliche Referenzen erhalten bleiben."""
        text = "Gemäß Art. 6 DSGVO und § 26 BDSG, Az. 1 ZR 140/22"

        # Keine Entitäten zum Anonymisieren
        doc = self.create_mock_doc(anonymizer_with_mock.nlp, text, [])
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text)

        # Alles sollte erhalten bleiben
        assert result.anonymized_text == text

    def test_hash_storage(self, anonymizer_with_mock):
        """Test dass Original-Namen als Hash gespeichert werden."""
        text = "Max Mustermann ist der Antragsteller."

        doc = self.create_mock_doc(
            anonymizer_with_mock.nlp, text, [("Max Mustermann", "PER", 0, 14)]
        )
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text)

        # Hash sollte gespeichert sein, nicht der Klartext
        assert "[Person 1]" in result.mappings
        mapping_value = result.mappings["[Person 1]"]
        assert len(mapping_value) == 64  # SHA256 Hash-Länge
        assert "Max Mustermann" not in mapping_value

    def test_complex_legal_text(self, anonymizer_with_mock):
        """Test mit komplexem rechtlichen Text."""
        text = """
        Der Kläger Herr Schmidt wendet sich gegen die Beklagte XYZ AG.
        Das OLG München hat mit Urteil vom 15.03.2024 (Az. 6 U 5042/19)
        entschieden. Der Zeuge Müller bestätigte die Aussage.
        """

        doc = self.create_mock_doc(
            anonymizer_with_mock.nlp,
            text.strip(),
            [
                ("Herr Schmidt", "PER", 11, 23),
                ("XYZ AG", "ORG", 56, 62),
                ("OLG München", "ORG", 72, 83),
                ("Müller", "PER", 167, 173),
            ],
        )
        anonymizer_with_mock.nlp.return_value = doc

        result = anonymizer_with_mock.anonymize(text.strip())

        # Prüfe Anonymisierung
        assert "[Person 1]" in result.anonymized_text  # Schmidt
        assert "[Person 2]" in result.anonymized_text  # Müller
        assert "[Organisation 1]" in result.anonymized_text  # XYZ AG

        # Prüfe Erhaltung
        assert "Kläger" in result.anonymized_text
        assert "Beklagte" in result.anonymized_text
        assert "OLG München" in result.anonymized_text  # Gericht erhalten
        assert "6 U 5042/19" in result.anonymized_text  # Az erhalten

    def test_empty_text(self, anonymizer_with_mock):
        """Test mit leerem Text."""
        result = anonymizer_with_mock.anonymize("")

        assert result.anonymized_text == ""
        assert len(result.mappings) == 0
        assert len(result.entity_types) == 0

    def test_bulk_anonymize(self, anonymizer_with_mock):
        """Test der Bulk-Anonymisierung."""
        texts = ["Max Mustermann klagt.", "Erika Musterfrau ist Zeugin.", ""]

        # Mock für jeden Text
        docs = [
            self.create_mock_doc(
                anonymizer_with_mock.nlp, texts[0], [("Max Mustermann", "PER", 0, 14)]
            ),
            self.create_mock_doc(
                anonymizer_with_mock.nlp, texts[1], [("Erika Musterfrau", "PER", 0, 16)]
            ),
            self.create_mock_doc(anonymizer_with_mock.nlp, texts[2], []),
        ]

        anonymizer_with_mock.nlp.side_effect = docs

        results = anonymizer_with_mock.bulk_anonymize(texts)

        assert len(results) == 3
        assert "[Person 1]" in results[0].anonymized_text
        assert "[Person 1]" in results[1].anonymized_text  # Neuer Counter pro Text
        assert results[2].anonymized_text == ""

    def test_statistics(self, anonymizer_with_mock):
        """Test der Statistik-Funktionalität."""
        text = "Max Mustermann von der ABC GmbH in Berlin."

        doc = self.create_mock_doc(
            anonymizer_with_mock.nlp,
            text,
            [
                ("Max Mustermann", "PER", 0, 14),
                ("ABC GmbH", "ORG", 23, 31),
                ("Berlin", "LOC", 35, 41),
            ],
        )
        anonymizer_with_mock.nlp.return_value = doc

        anonymizer_with_mock.anonymize(text, anonymize_orgs=True, anonymize_locations=True)

        stats = anonymizer_with_mock.get_statistics()

        assert stats["texts_processed"] == 1
        assert stats["names_anonymized"] == 1
        assert stats["organizations_anonymized"] == 1
        assert stats["locations_anonymized"] == 1

    @pytest.mark.skipif(
        not pytest.importorskip("spacy", reason="spaCy nicht installiert"),
        reason="spaCy ist erforderlich",
    )
    def test_real_spacy_integration(self):
        """Integration-Test mit echtem spaCy-Modell (wenn verfügbar)."""
        try:
            anonymizer = GermanLegalAnonymizer()

            text = "Der Kläger Hans Müller verklagt die Beklagte Anna Schmidt."
            result = anonymizer.anonymize(text)

            # Mindestens grundlegende Funktionalität prüfen
            assert isinstance(result, AnonymizationResult)
            assert result.anonymized_text is not None

        except RuntimeError as e:
            if "spacy model" in str(e).lower():
                pytest.skip("spaCy Modell 'de_core_news_sm' nicht installiert")
