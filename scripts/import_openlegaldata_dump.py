#!/usr/bin/env python3
"""
OpenLegalData Dump Import Script (Modularisiert).

Schlanke Version mit modularer Architektur.
Nutzt die neuen Module aus src/ für bessere Wartbarkeit.

Verwendung:
  python scripts/import_openlegaldata_dump.py --input cases.json --limit 500
  python scripts/import_openlegaldata_dump.py --examples
  python scripts/import_openlegaldata_dump.py --download
"""

import sys
from pathlib import Path

# Füge src/ zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cli.commands import cli


if __name__ == "__main__":
    # CLI ausführen
    cli()
