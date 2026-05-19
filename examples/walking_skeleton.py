#!/usr/bin/env python3
"""Walking-skeleton demo for datenschutz-rechtsprechung-api.

Runs the project's core text-processing pipeline against a small bundled
fixture decision — no database, no Redis, no HTTP, no spaCy model download.
The goal is the README's "fastest verifiable path" claim: a single command
that exercises the moving parts and prints something meaningful.

What it does, in order:
    1. Loads a short fixture text (anonymised redaction of a real-style
       German data-protection ruling — invented details, no real persons).
    2. Runs the regex-fallback anonymiser (SimpleGermanLegalAnonymizer)
       and shows what was redacted.
    3. Runs the GDPR article extractor and prints the references it found.
    4. Returns a non-zero exit code if either stage produced no output, so
       it can be wired into CI as a smoke test.

The full pipeline (PostgreSQL persistence, Celery jobs, FastAPI search,
spaCy-NER anonymisation) is covered by the test suite — see
`docs/quickstart/QUICK_START.md` and `tests/`.

Usage:
    python examples/walking_skeleton.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src` importable when the script is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzers.gdpr_extractor import GDPRArticleExtractor
from src.processors.anonymizer import SimpleGermanLegalAnonymizer


# A short, invented fixture in the style of a real German data-protection
# ruling. Personal details are fictional; the legal references are real
# (Art. 6, 15, 82 GDPR; §15 BDSG).
FIXTURE = """
Az.: 12 O 345/24

Der Kläger Max Mustermann, geboren am 03.04.1978, wohnhaft in
Beispielstraße 7, 10115 Berlin, verlangt von der Beklagten Auskunft
nach Art. 15 DSGVO und Schadensersatz gemäß Art. 82 DSGVO sowie §15
BDSG.

Die Beklagte, vertreten durch ihren Geschäftsführer Hans Müller,
verarbeitet personenbezogene Daten ohne ausreichende Rechtsgrundlage
im Sinne von Art. 6 Abs. 1 DSGVO. Telefonisch erreichbar unter
+49 30 1234567, per E-Mail an info@beispiel.de.
""".strip()


def main() -> int:
    print("walking-skeleton — datenschutz-rechtsprechung-api")
    print("=" * 52)
    print()

    # Stage 1: anonymisation (regex fallback — no spaCy model required).
    print("[1/2] anonymiser (regex fallback)")
    anonymiser = SimpleGermanLegalAnonymizer()
    result = anonymiser.anonymize(FIXTURE)
    redacted_text = getattr(result, "anonymized_text", result)
    replacements = getattr(result, "replacements", None)

    print(f"      input length  : {len(FIXTURE)} chars")
    print(f"      output length : {len(redacted_text)} chars")
    if replacements:
        print(f"      replacements  : {len(replacements)}")
    print("      first 300 chars of redacted output:")
    for line in redacted_text[:300].splitlines():
        print(f"        | {line}")
    print()

    # Stage 2: legal-reference extraction (regex-based, deterministic).
    print("[2/2] gdpr-article extractor")
    extractor = GDPRArticleExtractor()
    gdpr_articles, bdsg_sections = extractor.extract_all(FIXTURE)
    references = gdpr_articles + bdsg_sections
    print(f"      DSGVO articles : {len(gdpr_articles)}")
    print(f"      BDSG sections  : {len(bdsg_sections)}")
    for reference in references[:10]:
        print(f"        - {reference}")
    print()

    # Smoke-test gate: both stages must have produced something useful.
    ok = bool(redacted_text) and bool(references)
    print("result:", "OK" if ok else "EMPTY (smoke-test failed)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
