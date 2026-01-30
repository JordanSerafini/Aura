#!/usr/bin/env python3
"""
AURA-OS Agent: Logger Master
Team: Core System
Description: Agent central de logging - écrit des logs formatés en Markdown
"""

import argparse
import os
from datetime import datetime
from pathlib import Path

LOGS_BASE = Path.home() / "aura_logs"

TEAMS = {
    "cyber": "Team Cyber",
    "pc-admin": "Team PC-Admin",
    "info-data": "Team Info-Data",
    "vocal-ui": "Team Vocal-UI",
    "core": "Core System"
}

def get_log_file(team: str) -> Path:
    """Retourne le chemin du fichier log du jour pour une équipe."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_dir = LOGS_BASE / today
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{team}.md"

def log_entry(team: str, agent: str, status: str, message: str, details: str = None):
    """Écrit une entrée de log formatée en Markdown."""
    log_file = get_log_file(team)
    timestamp = datetime.now().strftime("%H:%M:%S")

    # Emoji selon le status
    status_emoji = {
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
        "start": "🚀",
        "complete": "🏁"
    }.get(status.lower(), "📝")

    # Créer l'en-tête du fichier si nouveau
    if not log_file.exists():
        header = f"""# {TEAMS.get(team, team)} - Logs du {datetime.now().strftime("%d/%m/%Y")}

---

"""
        log_file.write_text(header)

    # Construire l'entrée
    entry = f"\n### [{timestamp}] {status_emoji} {agent}\n"
    entry += f"**Status:** `{status.upper()}`\n\n"
    entry += f"{message}\n"

    if details:
        entry += f"\n```\n{details}\n```\n"

    entry += "\n---\n"

    # Ajouter au fichier
    with open(log_file, "a") as f:
        f.write(entry)

    print(f"{status_emoji} [{team}] {agent}: {message}")
    return str(log_file)

def main():
    parser = argparse.ArgumentParser(description="AURA-OS Logger Master")
    parser.add_argument("--team", required=True, choices=list(TEAMS.keys()),
                        help="Équipe source du log")
    parser.add_argument("--agent", required=True, help="Nom de l'agent")
    parser.add_argument("--status", required=True,
                        choices=["success", "error", "warning", "info", "start", "complete"],
                        help="Status de l'opération")
    parser.add_argument("--message", required=True, help="Message principal")
    parser.add_argument("--details", help="Détails supplémentaires (code, output, etc.)")

    args = parser.parse_args()

    log_path = log_entry(
        team=args.team,
        agent=args.agent,
        status=args.status,
        message=args.message,
        details=args.details
    )

    print(f"Log écrit dans: {log_path}")

if __name__ == "__main__":
    main()
