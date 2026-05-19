#!/usr/bin/env python3
"""
Test-Script für Schweizer Gerichtsentscheidungen von Hugging Face.

Lädt das Swiss Judgment Prediction Dataset und analysiert es.
"""

import json
import sys
from pathlib import Path
from collections import Counter

# Füge src/ zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_swiss_dataset():
    """Lädt und analysiert das Schweizer Dataset von Hugging Face."""

    print("=" * 60)
    print("🇨🇭 SCHWEIZER GERICHTSENTSCHEIDUNGEN - HUGGING FACE TEST")
    print("=" * 60)

    try:
        from datasets import load_dataset

        print("\n📥 Lade Dataset von Hugging Face...")
        print("   Dataset: rcds/swiss_judgment_prediction")
        print("   Dies kann beim ersten Mal einige Minuten dauern...")

        # Lade das Dataset (neues Format ohne Config)
        try:
            # Versuche neues Format
            dataset = load_dataset("rcds/swiss_judgment_prediction", trust_remote_code=True)
        except:
            # Fallback: Alternative Methode
            dataset = load_dataset("rcds/swiss_judgment_prediction")

        # Basis-Statistiken
        print("\n📊 Dataset-Statistiken:")
        print(f"   • Training:   {len(dataset['train']):,} Fälle")
        print(f"   • Validation: {len(dataset['validation']):,} Fälle")
        print(f"   • Test:       {len(dataset['test']):,} Fälle")
        print(
            f"   • GESAMT:     {len(dataset['train']) + len(dataset['validation']) + len(dataset['test']):,} Fälle"
        )

        # Sprach-Verteilung
        train_data = dataset["train"]
        languages = Counter(train_data["language"])
        print("\n🌍 Sprach-Verteilung (Training):")
        for lang, count in languages.most_common():
            percentage = (count / len(train_data)) * 100
            lang_name = {"de": "Deutsch", "fr": "Französisch", "it": "Italienisch"}.get(lang, lang)
            print(f"   • {lang_name:12s}: {count:6,} ({percentage:.1f}%)")

        # Jahr-Verteilung
        years = Counter(train_data["year"])
        min_year = min(years.keys())
        max_year = max(years.keys())
        print(f"\n📅 Zeitraum: {min_year} - {max_year}")

        # Rechtsgebiete
        legal_areas = Counter(train_data["legal area"])
        print("\n⚖️ Top 10 Rechtsgebiete:")
        for area, count in legal_areas.most_common(10):
            percentage = (count / len(train_data)) * 100
            print(f"   • {area:30s}: {count:6,} ({percentage:.1f}%)")

        # Kantone
        cantons = Counter(train_data["canton"])
        print(f"\n🏛️ Anzahl vertretener Kantone: {len(cantons)}")
        print("   Top 5 Kantone:")
        for canton, count in cantons.most_common(5):
            percentage = (count / len(train_data)) * 100
            print(f"   • {canton:5s}: {count:6,} ({percentage:.1f}%)")

        # Label-Verteilung (Urteilsausgang)
        labels = Counter(train_data["labels"])
        print("\n⚖️ Urteilsausgang-Verteilung:")
        for label, count in labels.items():
            percentage = (count / len(train_data)) * 100
            outcome = "Abweisung" if label == 0 else "Gutheissung"
            print(f"   • {outcome:12s}: {count:6,} ({percentage:.1f}%)")

        # Beispiel-Dokument analysieren
        print("\n📄 BEISPIEL-DOKUMENT (ID: 0):")
        print("-" * 40)
        example = train_data[0]
        print(f"ID:          {example['id']}")
        print(f"Jahr:        {example['year']}")
        print(f"Sprache:     {example['language']}")
        print(f"Kanton:      {example['canton']}")
        print(f"Region:      {example['region']}")
        print(f"Rechtsgebiet: {example['legal area']}")
        print(f"Ausgang:     {'Abweisung' if example['labels'] == 0 else 'Gutheissung'}")
        print(f"Text-Länge:  {len(example['facts'])} Zeichen")
        print(f"Text-Anfang: {example['facts'][:200]}...")

        # Datenschutz-Relevanz prüfen
        print("\n🔍 DATENSCHUTZ-RELEVANZ-ANALYSE:")
        print("-" * 40)

        # Suche nach Datenschutz-Keywords
        keywords = {
            "DSG": 0,
            "Datenschutz": 0,
            "Persönlichkeit": 0,
            "personenbezogen": 0,
            "EDÖB": 0,
            "Privacy": 0,
            "DSGVO": 0,
            "GDPR": 0,
        }

        sample_size = min(1000, len(train_data))
        print(f"Analysiere {sample_size} Dokumente auf Datenschutz-Bezug...")

        for i in range(sample_size):
            text = train_data[i]["facts"].lower()
            for keyword in keywords:
                if keyword.lower() in text:
                    keywords[keyword] += 1

        print("\nKeyword-Treffer:")
        total_relevant = 0
        relevant_docs = set()
        for keyword, count in sorted(keywords.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / sample_size) * 100
            print(f"   • {keyword:20s}: {count:4} ({percentage:.1f}%)")
            if count > 0:
                # Zähle Dokumente mit mindestens einem Treffer
                for i in range(sample_size):
                    if keyword.lower() in train_data[i]["facts"].lower():
                        relevant_docs.add(i)

        total_relevant = len(relevant_docs)
        relevance_rate = (total_relevant / sample_size) * 100
        print(f"\n📊 Datenschutz-Relevanz: {total_relevant}/{sample_size} ({relevance_rate:.1f}%)")

        # Exportiere Sample als JSON
        print("\n💾 EXPORT-TEST:")
        print("-" * 40)

        sample_for_export = []
        for i in range(min(10, len(train_data))):
            doc = train_data[i]
            sample_for_export.append(
                {
                    "id": str(doc["id"]),
                    "year": doc["year"],
                    "text": doc["facts"],
                    "language": doc["language"],
                    "canton": doc["canton"],
                    "region": doc["region"],
                    "legal_area": doc["legal area"],
                    "court": "Bundesgericht",  # Swiss Federal Supreme Court
                    "label": doc["labels"],
                    "source": "swiss_judgment_prediction",
                }
            )

        output_file = Path("swiss_sample.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(sample_for_export, f, ensure_ascii=False, indent=2)

        print(f"✅ Sample exportiert nach: {output_file}")
        print(f"   Enthält {len(sample_for_export)} Dokumente")

        # Test mit unserem Importer
        print("\n🔧 TEST MIT SWISS IMPORTER:")
        print("-" * 40)

        try:
            from src.importers.swiss_datasets import SwissDatasetImporter

            importer = SwissDatasetImporter()

            # Test Relevanz-Scoring
            test_doc = {
                "text": train_data[0]["facts"],
                "court": "Bundesgericht",
                "legal_area": train_data[0]["legal area"],
            }

            score = importer.calculate_relevance_score(test_doc)
            print(f"Relevanz-Score für erstes Dokument: {score}")

            # Test Parsing
            parsed = importer.parse_document(sample_for_export[0])
            if parsed:
                print("✅ Dokument erfolgreich geparst")
                print(f"   • Titel: {parsed.title[:50]}...")
                print(f"   • Gericht: {parsed.court}")
                print(f"   • Datum: {parsed.decision_date}")
            else:
                print("❌ Parsing fehlgeschlagen")

        except ImportError as e:
            print(f"⚠️ Swiss Importer Test übersprungen: {e}")

        print("\n" + "=" * 60)
        print("✅ SCHWEIZER DATASET-TEST ABGESCHLOSSEN!")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ FEHLER: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_swiss_dataset()
    sys.exit(0 if success else 1)
