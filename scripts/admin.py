#!/usr/bin/env python
"""
Datenschutz-Rechtsprechung API Admin CLI Tool.
Pragmatisches Command-Line Interface für administrative Aufgaben.
"""

import asyncio
import click
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import db_manager, Decision
from src.config import settings
from sqlalchemy import select, func, and_, delete
from sqlalchemy.orm import selectinload
import httpx
from rich.console import Console
from rich.table import Table
from rich.progress import track
from rich import box

console = Console()


@click.group()
def cli():
    """Datenschutz-Rechtsprechung API Admin CLI - Verwaltungstool für Administratoren."""
    pass


@cli.command()
@click.option(
    "--format", type=click.Choice(["table", "json"]), default="table", help="Ausgabeformat"
)
def stats(format):
    """Zeigt detaillierte Statistiken über die Datenbank."""

    async def get_stats():
        await db_manager.initialize()

        async for session in db_manager.get_session():
            # Gesamt-Statistiken
            total = await session.scalar(select(func.count(Decision.id)))

            # Nach Quelle
            by_source = await session.execute(
                select(Decision.source, func.count(Decision.id)).group_by(Decision.source)
            )

            # Nach Gericht (Top 10)
            by_court = await session.execute(
                select(Decision.court, func.count(Decision.id))
                .group_by(Decision.court)
                .order_by(func.count(Decision.id).desc())
                .limit(10)
            )

            # Letzte 24h
            yesterday = datetime.utcnow() - timedelta(days=1)
            last_24h = await session.scalar(
                select(func.count(Decision.id)).where(Decision.created_at >= yesterday)
            )

            # Letzte Woche
            last_week = datetime.utcnow() - timedelta(days=7)
            last_7d = await session.scalar(
                select(func.count(Decision.id)).where(Decision.created_at >= last_week)
            )

            return {
                "total": total,
                "last_24h": last_24h,
                "last_7d": last_7d,
                "by_source": dict(by_source.all()),
                "by_court": dict(by_court.all()),
            }

    stats_data = asyncio.run(get_stats())

    if format == "json":
        console.print_json(data=stats_data)
    else:
        # Übersichts-Tabelle
        overview_table = Table(
            title="📊 Datenschutz-Rechtsprechung API Statistiken", box=box.ROUNDED
        )
        overview_table.add_column("Metrik", style="cyan", no_wrap=True)
        overview_table.add_column("Wert", style="green", justify="right")

        overview_table.add_row("Gesamt Entscheidungen", f"{stats_data['total']:,}")
        overview_table.add_row("Letzte 24 Stunden", f"{stats_data['last_24h']:,}")
        overview_table.add_row("Letzte 7 Tage", f"{stats_data['last_7d']:,}")

        console.print(overview_table)

        # Quellen-Tabelle
        source_table = Table(title="🌐 Nach Datenquelle", box=box.ROUNDED)
        source_table.add_column("Quelle", style="cyan")
        source_table.add_column("Anzahl", style="green", justify="right")

        for source, count in stats_data["by_source"].items():
            source_table.add_row(source or "Unbekannt", f"{count:,}")

        console.print(source_table)

        # Top Gerichte
        court_table = Table(title="⚖️ Top 10 Gerichte", box=box.ROUNDED)
        court_table.add_column("Gericht", style="cyan")
        court_table.add_column("Anzahl", style="green", justify="right")

        for court, count in stats_data["by_court"].items():
            court_table.add_row(court or "Unbekannt", f"{count:,}")

        console.print(court_table)


@cli.command()
@click.argument("source", type=click.Choice(["gdprhub", "openlegaldata", "all"]))
@click.option("--limit", default=10, help="Maximale Anzahl zu crawlender Seiten")
@click.option("--resume/--no-resume", default=True, help="Vorherigen Crawl fortsetzen")
def crawl(source, limit, resume):
    """Startet einen Crawler für die angegebene Datenquelle."""

    console.print(f"[yellow]⚠️ Crawler-Start über API...[/yellow]")

    async def start_crawl():
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # FastAPI Endpoint für Crawler-Start nutzen
                response = await client.post(
                    f"http://localhost:8000/crawl/{source}", json={"limit": limit, "resume": resume}
                )

                if response.status_code == 200:
                    result = response.json()
                    console.print(f"[green]✅ Crawler gestartet![/green]")
                    console.print(f"Task ID: {result.get('task_id', 'N/A')}")
                    console.print(f"Status: {result.get('status', 'N/A')}")
                else:
                    console.print(f"[red]❌ Fehler: {response.text}[/red]")

            except httpx.ConnectError:
                console.print("[red]❌ FastAPI Server nicht erreichbar. Starte mit:[/red]")
                console.print("[yellow]uvicorn src.api.main:app --reload[/yellow]")
            except Exception as e:
                console.print(f"[red]❌ Fehler: {e}[/red]")

    asyncio.run(start_crawl())


@cli.command()
@click.option("--older-than", default=30, help="Entscheidungen älter als X Tage löschen")
@click.option("--source", help="Nur Entscheidungen dieser Quelle löschen")
@click.option("--dry-run/--execute", default=True, help="Nur anzeigen was gelöscht würde")
@click.confirmation_option(prompt="Wirklich alte Daten löschen?")
def clean(older_than, source, dry_run):
    """Bereinigt alte oder unnötige Daten aus der Datenbank."""

    async def clean_data():
        await db_manager.initialize()

        cutoff_date = datetime.utcnow() - timedelta(days=older_than)

        async for session in db_manager.get_session():
            # Query aufbauen
            query = select(Decision).where(Decision.created_at < cutoff_date)

            if source:
                query = query.where(Decision.source == source)

            # Zählen
            count_query = select(func.count(Decision.id)).where(Decision.created_at < cutoff_date)
            if source:
                count_query = count_query.where(Decision.source == source)

            count = await session.scalar(count_query)

            if dry_run:
                console.print(f"[yellow]🔍 Dry-Run Modus[/yellow]")
                console.print(f"Würde {count:,} Entscheidungen löschen")

                # Beispiele zeigen
                examples = await session.execute(query.limit(5))
                console.print("\nBeispiele:")
                for decision in examples.scalars():
                    console.print(f"  - {decision.title[:60]}... ({decision.created_at.date()})")
            else:
                if count > 0:
                    # Löschen
                    delete_stmt = delete(Decision).where(Decision.created_at < cutoff_date)
                    if source:
                        delete_stmt = delete_stmt.where(Decision.source == source)

                    await session.execute(delete_stmt)
                    await session.commit()

                    console.print(f"[green]✅ {count:,} Entscheidungen gelöscht[/green]")
                else:
                    console.print("[yellow]Keine Entscheidungen zum Löschen gefunden[/yellow]")

    asyncio.run(clean_data())


@cli.command()
@click.option(
    "--format", type=click.Choice(["excel", "csv", "json"]), default="excel", help="Export-Format"
)
@click.option("--output", default="export", help="Ausgabe-Dateiname (ohne Endung)")
@click.option("--limit", default=1000, help="Maximale Anzahl zu exportierender Einträge")
@click.option("--source", help="Nur Entscheidungen dieser Quelle exportieren")
def export(format, output, limit, source):
    """Exportiert Entscheidungen in verschiedene Formate."""

    async def export_data():
        await db_manager.initialize()

        async for session in db_manager.get_session():
            # Query aufbauen
            query = select(Decision).limit(limit)

            if source:
                query = query.where(Decision.source == source)

            result = await session.execute(query)
            decisions = result.scalars().all()

            # In DataFrame konvertieren
            data = []
            for d in decisions:
                data.append(
                    {
                        "ID": str(d.id),  # Convert UUID to string
                        "Titel": d.title,
                        "Gericht": d.court,
                        "Aktenzeichen": d.case_number,
                        "Datum": d.decision_date.isoformat() if d.decision_date else None,
                        "Quelle": d.source,
                        "DSGVO-Artikel": ", ".join(d.gdpr_articles) if d.gdpr_articles else "",
                        "URL": d.source_url,
                        "Erstellt": d.created_at.isoformat(),
                    }
                )

            df = pd.DataFrame(data)

            # Exportieren
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{output}_{timestamp}"

            if format == "excel":
                filepath = f"{filename}.xlsx"
                df.to_excel(filepath, index=False, engine="openpyxl")
                console.print(f"[green]✅ Exportiert nach {filepath}[/green]")

            elif format == "csv":
                filepath = f"{filename}.csv"
                df.to_csv(filepath, index=False, encoding="utf-8-sig")
                console.print(f"[green]✅ Exportiert nach {filepath}[/green]")

            elif format == "json":
                filepath = f"{filename}.json"
                # Use json.dumps to handle encoding properly
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                console.print(f"[green]✅ Exportiert nach {filepath}[/green]")

            console.print(f"[cyan]📊 {len(df):,} Entscheidungen exportiert[/cyan]")

    asyncio.run(export_data())


@cli.command()
def health():
    """Zeigt den Gesundheitsstatus aller Systeme."""

    async def check_health():
        health_data = {}

        # FastAPI Health Check
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://localhost:8000/system/health")
                health_data["fastapi"] = (
                    response.json() if response.status_code == 200 else {"status": "unhealthy"}
                )
        except:
            health_data["fastapi"] = {"status": "offline"}

        # Flask Health Check
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://localhost:5001/health")
                health_data["flask"] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy"
                }
        except:
            health_data["flask"] = {"status": "offline"}

        # Database Check
        try:
            await db_manager.initialize()
            async for session in db_manager.get_session():
                await session.execute(select(1))
                health_data["database"] = {"status": "healthy"}
        except:
            health_data["database"] = {"status": "unhealthy"}

        return health_data

    health = asyncio.run(check_health())

    # Status-Tabelle
    table = Table(title="🏥 System Health Status", box=box.ROUNDED)
    table.add_column("Service", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    # Status-Icons
    status_icons = {
        "healthy": "[green]✅ Healthy[/green]",
        "degraded": "[yellow]⚠️ Degraded[/yellow]",
        "unhealthy": "[red]❌ Unhealthy[/red]",
        "offline": "[red]🔌 Offline[/red]",
    }

    # FastAPI
    api_status = health["fastapi"].get("status", "unknown")
    table.add_row(
        "FastAPI", status_icons.get(api_status, "[dim]Unknown[/dim]"), f"http://localhost:8000"
    )

    # Flask
    flask_status = health["flask"].get("status", "unknown")
    table.add_row(
        "Flask Web-UI",
        status_icons.get(flask_status, "[dim]Unknown[/dim]"),
        f"http://localhost:5001",
    )

    # Database
    db_status = health["database"].get("status", "unknown")
    table.add_row(
        "PostgreSQL",
        status_icons.get(db_status, "[dim]Unknown[/dim]"),
        settings.database_url.split("@")[1] if "@" in settings.database_url else "localhost",
    )

    console.print(table)

    # Monitoring-Dashboard Link
    if health["fastapi"].get("status") == "healthy":
        console.print("\n[cyan]📊 Detailliertes Monitoring:[/cyan]")
        console.print("   http://localhost:8000/dashboard")
        console.print("   http://localhost:8000/docs")


@cli.command()
def info():
    """Zeigt nützliche Informationen und Links."""

    console.print("[bold cyan]Datenschutz-Rechtsprechung API Admin CLI[/bold cyan]")
    console.print("=" * 50)

    info_table = Table(box=box.SIMPLE)
    info_table.add_column("Resource", style="cyan")
    info_table.add_column("URL/Command", style="yellow")

    info_table.add_row("📊 Monitoring Dashboard", "http://localhost:8000/dashboard")
    info_table.add_row("📚 API Documentation", "http://localhost:8000/docs")
    info_table.add_row("🌐 Web UI", "http://localhost:5001")
    info_table.add_row("🔧 FastAPI starten", "uvicorn src.api.main:app --reload")
    info_table.add_row("🌐 Flask starten", "./scripts/start_web_dev.sh")
    info_table.add_row("🐳 Docker starten", "docker-compose up -d")

    console.print(info_table)

    console.print("\n[bold]Verfügbare Befehle:[/bold]")
    console.print("  stats   - Zeige Datenbank-Statistiken")
    console.print("  crawl   - Starte Crawler")
    console.print("  clean   - Bereinige alte Daten")
    console.print("  export  - Exportiere Daten")
    console.print("  health  - Prüfe System-Status")
    console.print("  info    - Diese Übersicht")
    console.print("  claude-analysis  - Claude Code Log Analysis")
    console.print("  claude-health    - System Health Score")
    console.print("  claude-logs      - Recent Critical Events")


# Claude Code Monitoring Commands


@cli.command("claude-analysis")
@click.option(
    "--format", type=click.Choice(["json", "summary"]), default="json", help="Ausgabeformat"
)
@click.option("--days", default=1, help="Analysiere Events der letzten N Tage")
def claude_analysis(format, days):
    """Führe Claude Code Log Analysis durch und gebe strukturierte Ergebnisse zurück."""

    import subprocess
    import sys
    from pathlib import Path

    try:
        # Führe daily_analysis.py aus und capture output
        script_path = Path(__file__).parent / "claude_analysis" / "daily_analysis.py"

        if not script_path.exists():
            console.print("[red]❌ Claude Analysis Script nicht gefunden[/red]")
            sys.exit(1)

        # Führe Analysis aus
        result = subprocess.run(
            [sys.executable, str(script_path)], capture_output=True, text=True, timeout=60
        )

        if result.returncode != 0:
            console.print(f"[red]❌ Analysis fehlgeschlagen: {result.stderr}[/red]")
            sys.exit(1)

        # Lade generierte JSON-Datei
        analysis_file = Path(
            "data/logs/claude_analysis/daily_analysis_"
            + datetime.now().strftime("%Y-%m-%d")
            + ".json"
        )

        if analysis_file.exists():
            with open(analysis_file, "r", encoding="utf-8") as f:
                analysis_data = json.load(f)

            if format == "json":
                # Strukturierte JSON-Ausgabe für Web-Integration
                console.print_json(data=analysis_data)
            else:
                # Human-readable Summary
                metadata = analysis_data.get("metadata", {})
                health = analysis_data.get("system_health", {})
                performance = analysis_data.get("performance_analysis", {})

                console.print(f"[bold cyan]📊 Claude Code Analysis Summary[/bold cyan]")
                console.print(f"Date: {metadata.get('analysis_date', 'Unknown')}")
                console.print(f"Events: {metadata.get('total_events', 0)}")
                console.print(
                    f"Health Score: {health.get('health_score', 'Unknown')}/100 ({health.get('status', 'unknown')})"
                )
                console.print(
                    f"Performance Events: {performance.get('total_performance_events', 0)}"
                )

                # Critical Events
                critical_events = analysis_data.get("claude_priority_events", [])
                if critical_events:
                    console.print(f"\n[red]🚨 {len(critical_events)} Critical Events:[/red]")
                    for event in critical_events[:5]:  # Top 5
                        console.print(
                            f"  • {event.get('component', 'Unknown')}: {event.get('message', 'No message')}"
                        )
        else:
            console.print(
                "[yellow]⚠️ Keine Analysis-Daten gefunden. Führe erst eine Analysis durch.[/yellow]"
            )

    except subprocess.TimeoutExpired:
        console.print("[red]❌ Analysis-Timeout nach 60 Sekunden[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Fehler bei Claude Analysis: {str(e)}[/red]")
        sys.exit(1)


@cli.command("claude-health")
@click.option(
    "--format", type=click.Choice(["json", "table"]), default="table", help="Ausgabeformat"
)
def claude_health(format):
    """Berechne aktuellen System Health Score basierend auf Claude Events."""

    from pathlib import Path
    import glob

    try:
        # Lade aktuelle Analysis-Daten
        analysis_pattern = "data/logs/claude_analysis/daily_analysis_*.json"
        analysis_files = sorted(glob.glob(analysis_pattern), reverse=True)

        if not analysis_files:
            console.print("[yellow]⚠️ Keine Claude Analysis-Daten gefunden[/yellow]")
            return

        # Lade neueste Analysis
        with open(analysis_files[0], "r", encoding="utf-8") as f:
            analysis_data = json.load(f)

        health_data = analysis_data.get("system_health", {})
        performance_data = analysis_data.get("performance_analysis", {})
        error_data = analysis_data.get("error_analysis", {})

        health_summary = {
            "health_score": health_data.get("health_score", 0),
            "status": health_data.get("status", "unknown"),
            "total_events": health_data.get("total_events", 0),
            "error_events": health_data.get("error_events", 0),
            "error_rate": health_data.get("error_rate_percent", 0),
            "performance_issues": performance_data.get("total_performance_events", 0),
            "critical_operations": len(
                [
                    op
                    for op in performance_data.get("slowest_operations", [])
                    if op.get("duration_ms", 0) > 2000
                ]
            ),
        }

        if format == "json":
            console.print_json(data=health_summary)
        else:
            # Tabellen-Ausgabe
            health_table = Table(title="🏥 Claude System Health Score", box=box.ROUNDED)
            health_table.add_column("Metrik", style="cyan")
            health_table.add_column("Wert", style="green", justify="right")
            health_table.add_column("Status", justify="center")

            # Health Score mit Farbe
            score = health_summary["health_score"]
            if score >= 80:
                score_color = "[green]"
            elif score >= 60:
                score_color = "[yellow]"
            else:
                score_color = "[red]"

            score_end = score_color.replace("[", "[/")
            health_table.add_row(
                "Health Score",
                f"{score_color}{score}/100{score_end}",
                health_summary["status"].upper(),
            )
            health_table.add_row("Total Events (24h)", str(health_summary["total_events"]), "📊")
            health_table.add_row("Error Events", str(health_summary["error_events"]), "❌")
            health_table.add_row("Error Rate", f"{health_summary['error_rate']:.1f}%", "📈")
            health_table.add_row(
                "Performance Issues", str(health_summary["performance_issues"]), "⚡"
            )
            health_table.add_row(
                "Critical Operations", str(health_summary["critical_operations"]), "🚨"
            )

            console.print(health_table)

    except Exception as e:
        console.print(f"[red]❌ Fehler beim Health-Check: {str(e)}[/red]")
        sys.exit(1)


@cli.command("claude-logs")
@click.option(
    "--priority",
    type=click.Choice(["critical", "high", "medium", "low"]),
    default="critical",
    help="Mindest-Priorität der Events",
)
@click.option("--component", help="Filter nach Komponente (flask, fastapi, celery)")
@click.option("--hours", default=24, help="Events der letzten N Stunden")
@click.option(
    "--format", type=click.Choice(["json", "table"]), default="table", help="Ausgabeformat"
)
def claude_logs(priority, component, hours, format):
    """Zeige kritische Events aus Claude Logging System."""

    from pathlib import Path
    import glob
    from datetime import datetime, timedelta

    try:
        # Sammle JSONL-Log-Dateien
        log_pattern = "data/logs/claude_logging/*.jsonl"
        log_files = glob.glob(log_pattern)

        if not log_files:
            console.print("[yellow]⚠️ Keine Claude-Log-Dateien gefunden[/yellow]")
            return

        events = []
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Parse JSONL-Files
        for log_file in log_files:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            event = json.loads(line)

                            # Zeit-Filter
                            event_time = datetime.fromisoformat(
                                event.get("timestamp", "").replace("Z", "+00:00")
                            )
                            if event_time < cutoff_time:
                                continue

                            # Priority-Filter
                            event_priority = event.get("priority", "info")
                            priority_levels = ["info", "low", "medium", "high", "critical"]
                            if priority_levels.index(event_priority) < priority_levels.index(
                                priority
                            ):
                                continue

                            # Component-Filter
                            if component and event.get("component", "") != component:
                                continue

                            events.append(event)
            except Exception as e:
                console.print(f"[dim]Fehler beim Lesen von {log_file}: {e}[/dim]")

        # Sortiere nach Timestamp (neueste zuerst)
        events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        if format == "json":
            console.print_json(data=events[:50])  # Limit für Performance
        else:
            if not events:
                console.print(
                    f"[yellow]📭 Keine {priority} Events der letzten {hours}h gefunden[/yellow]"
                )
                return

            # Tabellen-Ausgabe
            events_table = Table(
                title=f"🚨 Claude Critical Events (letzte {hours}h)", box=box.ROUNDED
            )
            events_table.add_column("Zeit", style="dim", width=16)
            events_table.add_column("Component", style="cyan", width=12)
            events_table.add_column("Priority", justify="center", width=8)
            events_table.add_column("Message", style="white")

            for event in events[:20]:  # Top 20 Events
                timestamp = event.get("timestamp", "")[:16]  # YYYY-MM-DD HH:MM
                component = event.get("component", "unknown")
                priority_val = event.get("priority", "info").upper()
                message = event.get("message", "No message")[:60]  # Truncate

                # Priority Colors
                priority_colors = {
                    "CRITICAL": "[red]🔴 CRITICAL[/red]",
                    "HIGH": "[yellow]🟡 HIGH[/yellow]",
                    "MEDIUM": "[blue]🔵 MEDIUM[/blue]",
                    "LOW": "[dim]⚪ LOW[/dim]",
                }

                events_table.add_row(
                    timestamp, component, priority_colors.get(priority_val, priority_val), message
                )

            console.print(events_table)
            console.print(f"\n[dim]Zeige {min(len(events), 20)} von {len(events)} Events[/dim]")

    except Exception as e:
        console.print(f"[red]❌ Fehler beim Lesen der Logs: {str(e)}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    cli()
