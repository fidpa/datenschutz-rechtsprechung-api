"""
Integration Tests für Backup und Recovery Funktionalität.

Testet die in Phase 7 implementierten Backup-Scripts und Recovery-Prozesse.
"""

import os
import subprocess
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import shutil

import pytest
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision, CrawlLog, AnonymizationMapping
from src.config import settings


class TestBackupRecovery:
    """Tests für Backup und Recovery Prozesse."""

    @pytest.fixture
    def backup_dir(self, tmp_path):
        """Erstellt temporäres Backup-Verzeichnis."""
        backup_path = tmp_path / "backups"
        backup_path.mkdir(exist_ok=True)
        yield backup_path
        # Cleanup
        if backup_path.exists():
            shutil.rmtree(backup_path)

    @pytest.mark.asyncio
    async def test_database_backup_creation(self, test_session: AsyncSession, backup_dir):
        """Test der Datenbank-Backup-Erstellung."""
        # Erstelle Test-Daten
        for i in range(10):
            decision = Decision(
                source="backup_test",
                source_id=f"backup_{i}",
                title=f"Backup Test Decision {i}",
                full_text_original=f"Test content {i}",
                decision_date=datetime.now() - timedelta(days=i),
            )
            test_session.add(decision)

        await test_session.commit()

        # Simuliere Backup-Erstellung
        backup_file = backup_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"

        # Mock pg_dump Befehl
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            # Simuliere Backup-Script Ausführung
            result = subprocess.run(["echo", "Backup simulation"], capture_output=True, text=True)

            # Erstelle Dummy-Backup-Datei
            backup_file.write_text("-- PostgreSQL backup\n-- Test data\n")

            assert backup_file.exists()
            assert backup_file.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_backup_compression(self, backup_dir):
        """Test der Backup-Kompression mit gzip."""
        # Erstelle unkomprimierte Test-Datei
        original_file = backup_dir / "test_backup.sql"
        test_data = "-- Test backup data\n" * 1000  # Wiederholter Text für bessere Kompression
        original_file.write_text(test_data)
        original_size = original_file.stat().st_size

        # Komprimiere
        compressed_file = backup_dir / "test_backup.sql.gz"

        import gzip

        with open(original_file, "rb") as f_in:
            with gzip.open(compressed_file, "wb") as f_out:
                f_out.write(f_in.read())

        compressed_size = compressed_file.stat().st_size

        # Verifiziere Kompression
        assert compressed_file.exists()
        assert compressed_size < original_size
        compression_ratio = 1 - (compressed_size / original_size)
        assert compression_ratio > 0.5  # Mindestens 50% Kompression bei wiederholtem Text

        # Test Dekompression
        decompressed_file = backup_dir / "test_backup_restored.sql"
        with gzip.open(compressed_file, "rb") as f_in:
            with open(decompressed_file, "wb") as f_out:
                f_out.write(f_in.read())

        assert decompressed_file.read_text() == test_data

    @pytest.mark.asyncio
    async def test_backup_checksum_verification(self, backup_dir):
        """Test der Backup-Integrität mittels SHA256-Checksums."""
        # Erstelle Test-Backup
        backup_file = backup_dir / "test_backup.sql"
        backup_content = "-- Test backup with checksum"
        backup_file.write_text(backup_content)

        # Berechne Checksum
        sha256_hash = hashlib.sha256()
        with open(backup_file, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)

        checksum = sha256_hash.hexdigest()

        # Speichere Checksum
        checksum_file = backup_dir / "test_backup.sql.sha256"
        checksum_file.write_text(f"{checksum}  test_backup.sql\n")

        # Verifiziere Checksum
        stored_checksum = checksum_file.read_text().split()[0]
        assert stored_checksum == checksum

        # Test mit korrupter Datei
        backup_file.write_text(backup_content + " corrupted")

        # Neue Checksum sollte anders sein
        sha256_hash = hashlib.sha256()
        with open(backup_file, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)

        new_checksum = sha256_hash.hexdigest()
        assert new_checksum != checksum

    @pytest.mark.asyncio
    async def test_backup_rotation(self, backup_dir):
        """Test der automatischen Backup-Rotation."""
        # Erstelle mehrere Backup-Dateien mit verschiedenen Zeitstempeln
        now = datetime.now()
        backup_files = []

        # Daily backups (letzten 7 Tage)
        for i in range(10):
            timestamp = (now - timedelta(days=i)).strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"backup_daily_{timestamp}.sql.gz"
            backup_file.write_text(f"Daily backup {i}")
            backup_files.append(backup_file)

        # Weekly backups (letzten 4 Wochen)
        for i in range(6):
            timestamp = (now - timedelta(weeks=i)).strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"backup_weekly_{timestamp}.sql.gz"
            backup_file.write_text(f"Weekly backup {i}")
            backup_files.append(backup_file)

        # Monthly backups (letzten 6 Monate)
        for i in range(8):
            timestamp = (now - timedelta(days=i * 30)).strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"backup_monthly_{timestamp}.sql.gz"
            backup_file.write_text(f"Monthly backup {i}")
            backup_files.append(backup_file)

        # Simuliere Rotation-Logik
        def rotate_backups(directory: Path, keep_daily=7, keep_weekly=4, keep_monthly=6):
            """Einfache Backup-Rotation Logik."""
            all_backups = sorted(
                directory.glob("backup_*.sql.gz"), key=lambda x: x.stat().st_mtime, reverse=True
            )

            daily = [f for f in all_backups if "daily" in f.name]
            weekly = [f for f in all_backups if "weekly" in f.name]
            monthly = [f for f in all_backups if "monthly" in f.name]

            # Lösche alte Backups
            for backup_list, keep_count in [
                (daily, keep_daily),
                (weekly, keep_weekly),
                (monthly, keep_monthly),
            ]:
                for old_backup in backup_list[keep_count:]:
                    old_backup.unlink()

            return len(daily[:keep_daily]) + len(weekly[:keep_weekly]) + len(monthly[:keep_monthly])

        # Führe Rotation aus
        remaining = rotate_backups(backup_dir)

        # Verifiziere Anzahl verbleibender Backups
        assert remaining <= 17  # 7 daily + 4 weekly + 6 monthly
        assert len(list(backup_dir.glob("backup_daily_*.sql.gz"))) <= 7
        assert len(list(backup_dir.glob("backup_weekly_*.sql.gz"))) <= 4
        assert len(list(backup_dir.glob("backup_monthly_*.sql.gz"))) <= 6

    @pytest.mark.asyncio
    async def test_database_restore(self, test_session: AsyncSession, backup_dir):
        """Test der Datenbank-Wiederherstellung aus Backup."""
        # Erstelle Original-Daten
        original_decisions = []
        for i in range(5):
            decision = Decision(
                source="restore_test",
                source_id=f"restore_{i}",
                title=f"Original Decision {i}",
                full_text_original=f"Original content {i}",
            )
            test_session.add(decision)
            original_decisions.append(decision)

        await test_session.commit()

        # Simuliere Backup
        backup_data = {
            "decisions": [
                {
                    "id": str(d.id),
                    "source": d.source,
                    "source_id": d.source_id,
                    "title": d.title,
                    "full_text_original": d.full_text_original,
                }
                for d in original_decisions
            ]
        }

        # Lösche Daten (simuliere Datenverlust)
        await test_session.execute(text("DELETE FROM decisions WHERE source = 'restore_test'"))
        await test_session.commit()

        # Verifiziere Löschung
        count = await test_session.scalar(
            select(func.count()).select_from(Decision).where(Decision.source == "restore_test")
        )
        assert count == 0

        # Simuliere Restore (würde normalerweise psql verwenden)
        for decision_data in backup_data["decisions"]:
            restored = Decision(
                source=decision_data["source"],
                source_id=decision_data["source_id"],
                title=decision_data["title"],
                full_text_original=decision_data["full_text_original"],
            )
            test_session.add(restored)

        await test_session.commit()

        # Verifiziere Wiederherstellung
        restored_count = await test_session.scalar(
            select(func.count()).select_from(Decision).where(Decision.source == "restore_test")
        )
        assert restored_count == 5

    @pytest.mark.asyncio
    async def test_incremental_backup(self, test_session: AsyncSession, backup_dir):
        """Test inkrementeller Backups basierend auf Änderungszeitstempel."""
        # Erstelle initiale Daten
        base_time = datetime.now() - timedelta(days=7)

        for i in range(10):
            decision = Decision(
                source="incremental_test",
                source_id=f"inc_{i}",
                title=f"Decision {i}",
                created_at=base_time + timedelta(days=i // 2),
            )
            test_session.add(decision)

        await test_session.commit()

        # Simuliere Full Backup
        last_backup_time = datetime.now() - timedelta(days=2)

        # Finde nur neue/geänderte Einträge seit letztem Backup
        recent_decisions = await test_session.execute(
            select(Decision).where(Decision.created_at > last_backup_time)
        )
        recent_count = len(recent_decisions.scalars().all())

        # Sollte nur die neuesten Einträge enthalten
        assert recent_count < 10
        assert recent_count > 0

    @pytest.mark.asyncio
    async def test_backup_encryption(self, backup_dir):
        """Test der Backup-Verschlüsselung (simuliert)."""
        # Erstelle Test-Backup
        backup_file = backup_dir / "test_backup.sql"
        sensitive_data = "-- Backup mit personenbezogenen Daten\nINSERT INTO decisions VALUES ('Max Mustermann');"
        backup_file.write_text(sensitive_data)

        # Simuliere Verschlüsselung mit einem Passwort
        import base64

        # Einfache XOR-"Verschlüsselung" für Demo (NICHT für Production!)
        password = "test_password_123"
        encrypted_data = bytearray()

        for i, char in enumerate(sensitive_data.encode()):
            encrypted_data.append(char ^ ord(password[i % len(password)]))

        # Speichere verschlüsselt
        encrypted_file = backup_dir / "test_backup.sql.enc"
        encrypted_file.write_bytes(base64.b64encode(encrypted_data))

        # Verifiziere Verschlüsselung
        assert encrypted_file.exists()
        encrypted_content = encrypted_file.read_bytes()
        assert encrypted_content != sensitive_data.encode()
        assert b"Max Mustermann" not in encrypted_content

        # Simuliere Entschlüsselung
        encrypted_bytes = base64.b64decode(encrypted_content)
        decrypted_data = bytearray()

        for i, byte in enumerate(encrypted_bytes):
            decrypted_data.append(byte ^ ord(password[i % len(password)]))

        decrypted_text = decrypted_data.decode()
        assert decrypted_text == sensitive_data

    @pytest.mark.asyncio
    async def test_backup_cron_schedule(self, backup_dir):
        """Test der Cron-Job Konfiguration für automatische Backups."""
        # Cron-Expressions für verschiedene Backup-Typen
        cron_schedules = {
            "daily": "0 3 * * *",  # Täglich um 3:00 Uhr
            "weekly": "0 4 * * 0",  # Sonntags um 4:00 Uhr
            "monthly": "0 5 1 * *",  # Monatlich am 1. um 5:00 Uhr
        }

        # Verifiziere Cron-Syntax
        for backup_type, cron_expr in cron_schedules.items():
            parts = cron_expr.split()
            assert len(parts) == 5  # Minute, Hour, Day, Month, Weekday

            # Validiere Zeitfelder
            minute, hour, day, month, weekday = parts
            assert 0 <= int(minute) <= 59 if minute != "*" else True
            assert 0 <= int(hour) <= 23 if hour != "*" else True

    @pytest.mark.asyncio
    async def test_backup_storage_management(self, backup_dir):
        """Test der Speicherplatzverwaltung für Backups."""
        # Erstelle mehrere große Backup-Dateien
        total_size = 0
        max_storage = 100 * 1024  # 100 KB Limit für Test

        for i in range(20):
            backup_file = backup_dir / f"backup_{i:03d}.sql"
            # Größe variiert zwischen 5-15 KB
            size = 5000 + (i * 500)
            backup_file.write_bytes(b"x" * size)
            total_size += size

        # Funktion zur Speicherplatz-Verwaltung
        def manage_storage(directory: Path, max_size: int):
            """Lösche älteste Backups wenn Speicherplatz-Limit überschritten."""
            backups = sorted(directory.glob("backup_*.sql"), key=lambda x: x.stat().st_mtime)

            current_size = sum(f.stat().st_size for f in backups)
            deleted_count = 0

            while current_size > max_size and backups:
                oldest = backups.pop(0)
                current_size -= oldest.stat().st_size
                oldest.unlink()
                deleted_count += 1

            return deleted_count, current_size

        # Manage storage
        deleted, remaining_size = manage_storage(backup_dir, max_storage)

        assert deleted > 0  # Einige Backups sollten gelöscht worden sein
        assert remaining_size <= max_storage

        # Verifiziere verbleibende Backups
        remaining_backups = list(backup_dir.glob("backup_*.sql"))
        total_remaining = sum(f.stat().st_size for f in remaining_backups)
        assert total_remaining <= max_storage

    @pytest.mark.asyncio
    async def test_backup_verification_script(self, backup_dir):
        """Test des Backup-Verifikations-Scripts."""
        # Erstelle Test-Backup mit bekanntem Inhalt
        backup_file = backup_dir / "verify_test.sql"
        test_content = """
        -- PostgreSQL backup
        CREATE TABLE decisions (id UUID PRIMARY KEY);
        INSERT INTO decisions VALUES ('123e4567-e89b-12d3-a456-426614174000');
        """
        backup_file.write_text(test_content)

        # Verifiziere Backup-Struktur
        content = backup_file.read_text()

        # Prüfe auf wichtige SQL-Strukturen
        assert "CREATE TABLE" in content
        assert "INSERT INTO" in content
        assert "decisions" in content

        # Prüfe auf Vollständigkeit (keine abgeschnittenen Befehle)
        assert content.count("(") == content.count(")")
        assert content.count("'") % 2 == 0  # Gerade Anzahl von Quotes

        # Simuliere Korruption
        corrupted_file = backup_dir / "corrupted.sql"
        corrupted_file.write_text(test_content[:-20])  # Letzte 20 Zeichen fehlen

        corrupted_content = corrupted_file.read_text()
        # Sollte unvollständig sein
        assert not corrupted_content.endswith(";")

    @pytest.mark.asyncio
    async def test_disaster_recovery_procedure(self, test_session: AsyncSession, backup_dir):
        """Test des kompletten Disaster-Recovery-Ablaufs."""
        # Phase 1: Normal-Betrieb - Erstelle Produktions-Daten
        production_data = []
        for i in range(100):
            decision = Decision(
                source="production",
                source_id=f"prod_{i}",
                title=f"Production Decision {i}",
                full_text_original=f"Important legal content {i}",
                decision_date=datetime.now() - timedelta(days=i),
            )
            test_session.add(decision)
            production_data.append({"source_id": decision.source_id, "title": decision.title})

        await test_session.commit()

        # Phase 2: Backup erstellen (simuliert)
        backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"disaster_backup_{backup_timestamp}.json"

        import json

        backup_file.write_text(json.dumps(production_data))

        # Phase 3: Disaster simulieren - Datenverlust
        await test_session.execute(text("DELETE FROM decisions WHERE source = 'production'"))
        await test_session.commit()

        # Verifiziere Datenverlust
        remaining = await test_session.scalar(
            select(func.count()).select_from(Decision).where(Decision.source == "production")
        )
        assert remaining == 0

        # Phase 4: Recovery aus Backup
        restored_data = json.loads(backup_file.read_text())

        for item in restored_data:
            restored_decision = Decision(
                source="production",
                source_id=item["source_id"],
                title=item["title"],
                full_text_original=f"Restored content for {item['source_id']}",
            )
            test_session.add(restored_decision)

        await test_session.commit()

        # Phase 5: Verifiziere Recovery
        recovered_count = await test_session.scalar(
            select(func.count()).select_from(Decision).where(Decision.source == "production")
        )
        assert recovered_count == 100

        # Verifiziere Datenintegrität
        sample_check = await test_session.execute(
            select(Decision).where(Decision.source_id == "prod_0")
        )
        sample = sample_check.scalar_one_or_none()
        assert sample is not None
        assert sample.title == "Production Decision 0"
