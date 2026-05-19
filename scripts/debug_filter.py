#!/usr/bin/env python3
"""Debug-Script um Filter-Problem zu untersuchen."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.importers.openlegaldata import OpenLegalDataImporter
from src.utils.file_handlers import DumpFileHandler
import json


def test_filter():
    """Testet die Filter-Logik mit echten Daten."""

    print("=== Filter Debug Test ===\n")

    # Importer initialisieren
    importer = OpenLegalDataImporter(verbose=True, min_score=3)
    file_handler = DumpFileHandler()

    # Erste 10 Dokumente aus der Datei lesen
    file_path = Path("cases_sample.jsonl.gz")

    print(f"Lese Dokumente aus {file_path}...")

    docs_processed = 0
    relevant_count = 0
    irrelevant_count = 0

    for idx, doc in enumerate(file_handler.open_file(file_path, offset=0)):
        if docs_processed >= 10:
            break

        # Relevanz berechnen
        score = importer.calculate_relevance_score(doc)
        is_relevant = importer.is_relevant(doc)
        doc_id = doc.get("id", "unknown")
        file_number = doc.get("file_number", "unknown")

        print(f"\nDokument {idx+1}:")
        print(f"  ID: {doc_id}")
        print(f"  Aktenzeichen: {file_number}")
        print(f"  Score: {score}")
        print(f"  Relevant: {is_relevant}")

        # Prüfe ob Keywords vorhanden sind
        content = doc.get("content", "") + " " + doc.get("name", "")
        has_datenschutz = "datenschutz" in content.lower()
        has_dsgvo = "dsgvo" in content.lower() or "gdpr" in content.lower()
        has_bdsg = "bdsg" in content.lower()
        has_personen = "personenbezogen" in content.lower()

        print(
            f"  Keywords: Datenschutz={has_datenschutz}, DSGVO/GDPR={has_dsgvo}, BDSG={has_bdsg}, Personenbezogen={has_personen}"
        )

        if is_relevant:
            relevant_count += 1
        else:
            irrelevant_count += 1

        docs_processed += 1

    print(f"\n=== Zusammenfassung ===")
    print(f"Dokumente verarbeitet: {docs_processed}")
    print(f"Relevant: {relevant_count}")
    print(f"Irrelevant: {irrelevant_count}")
    print(f"Filter funktioniert: {'JA' if irrelevant_count > 0 else 'NEIN'}")


if __name__ == "__main__":
    test_filter()
