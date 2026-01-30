#!/usr/bin/env python3
"""
AURA-OS Agent: Prompt Evolver
Team: Core
Description: Auto-amélioration continue du prompt système Aura
"""

import argparse
import json
import re
from pathlib import Path
from datetime import datetime
import subprocess

AURA_DIR = Path.home() / ".aura"
SYSTEM_FILE = AURA_DIR / "AURA_SYSTEM.md"
MANIFEST_FILE = AURA_DIR / "agents_manifest.json"
LOGS_DIR = Path.home() / "aura_logs"
BACKUP_DIR = AURA_DIR / "backups"


def backup_current():
    """Sauvegarde le prompt actuel"""
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"AURA_SYSTEM_{timestamp}.md"

    if SYSTEM_FILE.exists():
        backup_file.write_text(SYSTEM_FILE.read_text())
        print(f"💾 Backup: {backup_file.name}")
        return backup_file
    return None


def analyze_logs():
    """Analyse les logs pour trouver des patterns d'amélioration"""
    insights = {
        "agents_used": {},
        "errors": [],
        "suggestions": []
    }

    if not LOGS_DIR.exists():
        return insights

    # Parcourir les logs récents
    for day_dir in sorted(LOGS_DIR.iterdir(), reverse=True)[:7]:
        if not day_dir.is_dir():
            continue
        for log_file in day_dir.glob("*.md"):
            content = log_file.read_text()

            # Compter les agents utilisés
            for match in re.finditer(r'\[(\w+-?\w*)\] (\w+):', content):
                team, agent = match.groups()
                key = f"{team}/{agent}"
                insights["agents_used"][key] = insights["agents_used"].get(key, 0) + 1

            # Détecter les erreurs
            for line in content.split('\n'):
                if '❌' in line or 'error' in line.lower():
                    insights["errors"].append(line.strip())

    return insights


def sync_agents_in_doc():
    """Synchronise la liste des agents dans le doc avec le manifest"""
    if not MANIFEST_FILE.exists() or not SYSTEM_FILE.exists():
        return False

    manifest = json.loads(MANIFEST_FILE.read_text())
    agents = manifest.get("agents", [])

    # Grouper par team
    by_team = {}
    for agent in agents:
        team = agent.get("team", "core")
        if team not in by_team:
            by_team[team] = []
        by_team[team].append(agent)

    # Générer la nouvelle section
    section = ["## AGENTS DISPONIBLES ({} agents)\n".format(len(agents))]

    team_names = {
        "core": "Core System",
        "pc-admin": "Team PC-Admin",
        "cyber": "Team Cyber",
        "info-data": "Team Info-Data",
        "vocal-ui": "Team Vocal-UI"
    }

    for team_id, team_name in team_names.items():
        if team_id in by_team:
            section.append(f"\n### {team_name}")
            section.append("| Agent | Fichier | Description |")
            section.append("|-------|---------|-------------|")
            for agent in by_team[team_id]:
                section.append(f"| {agent.get('name', '?')} | `{agent.get('script', '?')}` | {agent.get('description', '')[:50]} |")

    new_section = "\n".join(section)

    # Remplacer dans le fichier
    content = SYSTEM_FILE.read_text()

    # Pattern pour trouver la section agents
    pattern = r'## AGENTS DISPONIBLES.*?(?=\n---|\n## [A-Z]|\Z)'

    if re.search(pattern, content, re.DOTALL):
        new_content = re.sub(pattern, new_section, content, flags=re.DOTALL)
        SYSTEM_FILE.write_text(new_content)
        print(f"✅ Section agents mise à jour ({len(agents)} agents)")
        return True

    return False


def add_new_rule(rule: str):
    """Ajoute une nouvelle règle au comportement"""
    if not SYSTEM_FILE.exists():
        return False

    content = SYSTEM_FILE.read_text()

    # Trouver la section COMPORTEMENT
    pattern = r'(## COMPORTEMENT\n)(.*?)(\n---)'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        new_rule = f"- **Nouvelle règle** : {rule}\n"
        new_section = match.group(1) + match.group(2) + new_rule + match.group(3)
        new_content = content[:match.start()] + new_section + content[match.end():]
        SYSTEM_FILE.write_text(new_content)
        print(f"✅ Règle ajoutée: {rule[:50]}...")
        return True

    return False


def evolve_report():
    """Génère un rapport d'évolution"""
    insights = analyze_logs()

    print("\n🧬 RAPPORT D'ÉVOLUTION AURA-OS")
    print("=" * 50)

    print("\n📊 Agents les plus utilisés:")
    sorted_agents = sorted(insights["agents_used"].items(), key=lambda x: x[1], reverse=True)[:5]
    for agent, count in sorted_agents:
        print(f"  • {agent}: {count} fois")

    if insights["errors"]:
        print(f"\n⚠️ Erreurs récentes ({len(insights['errors'])}):")
        for err in insights["errors"][:5]:
            print(f"  • {err[:60]}...")

    # Suggestions auto
    print("\n💡 Suggestions d'amélioration:")

    manifest = json.loads(MANIFEST_FILE.read_text()) if MANIFEST_FILE.exists() else {"agents": []}
    teams_with_agents = set(a.get("team") for a in manifest.get("agents", []))

    if "info-data" not in teams_with_agents:
        print("  • Team Info-Data est vide - créer des agents de veille/scraping")

    if len(manifest.get("agents", [])) < 10:
        print("  • Peu d'agents - envisager d'en créer plus pour l'automatisation")


def main():
    parser = argparse.ArgumentParser(description="Auto-évolution du système Aura-OS")
    parser.add_argument("command", nargs="?", default="report",
                       choices=["report", "sync", "backup", "add-rule", "restore"])
    parser.add_argument("--rule", "-r", help="Règle à ajouter")
    parser.add_argument("--backup-file", help="Fichier backup à restaurer")

    args = parser.parse_args()

    if args.command == "report":
        evolve_report()

    elif args.command == "sync":
        backup_current()
        sync_agents_in_doc()

    elif args.command == "backup":
        backup_current()

    elif args.command == "add-rule":
        if args.rule:
            backup_current()
            add_rule(args.rule)
        else:
            print("❌ Requis: --rule")

    elif args.command == "restore":
        if args.backup_file:
            backup = BACKUP_DIR / args.backup_file
            if backup.exists():
                SYSTEM_FILE.write_text(backup.read_text())
                print(f"✅ Restauré depuis {backup.name}")
        else:
            # Lister les backups
            if BACKUP_DIR.exists():
                backups = sorted(BACKUP_DIR.glob("*.md"), reverse=True)
                print("📁 Backups disponibles:")
                for b in backups[:10]:
                    print(f"  • {b.name}")


if __name__ == "__main__":
    main()
