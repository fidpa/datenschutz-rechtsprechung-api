"""Importer-Module fuer verschiedene Datenquellen."""

from .base import BaseImporter
from .openlegaldata import OpenLegalDataImporter

__all__ = ["BaseImporter", "OpenLegalDataImporter"]
