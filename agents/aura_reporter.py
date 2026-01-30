#!/usr/bin/env python3
"""
AURA Reporter - Agent de rapports quotidiens
Génère et maintient des rapports structurés de toutes les actions Aura.
Stocke dans ~/Desktop/rapports_aura/{jj-mm-aaaa}/
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Chemins
REPORTS_DIR = Path.home() / "Desktop" / "rapports_aura"
TODAY = datetime.now().strftime("%d-%m-%Y")
TODAY_DIR = REPORTS_DIR / TODAY
DAILY_SUMMARY = TODAY_DIR / "resume_quotidien.md"
ACTIONS_LOG = TODAY_DIR / "actions.md"
IMPROVEMENTS_LOG = TODAY_DIR / "ameliorations.md"
ERRORS_LOG = TODAY_DIR / "erreurs.md"
EBP_LOG = TODAY_DIR / "ebp_app.md"

def ensure_dirs():
    """Crée les répertoires si nécessaire"""
    TODAY_DIR.mkdir(parents=True, exist_ok=True)

def init_daily_files():
    """Initialise les fichiers du jour s'ils n'existent pas"""
    ensure_dirs()

    # Résumé quotidien
    if not DAILY_SUMMARY.exists():
        DAILY_SUMMARY.write_text(f"""# Rapport Aura - {TODAY}

## Vue d'ensemble
- **Date**: {datetime.now().strftime("%A %d %B %Y")}
- **Début journée**: {datetime.now().strftime("%H:%M")}
- **Statut**: 🟢 Actif

## Statistiques
| Métrique | Valeur |
|----------|--------|
| Actions effectuées | 0 |
| Erreurs | 0 |
| Améliorations | 0 |
| Builds EBP | 0 |

---
""")

    # Log des actions
    if not ACTIONS_LOG.exists():
        ACTIONS_LOG.write_text(f"""# Actions Aura - {TODAY}

| Heure | Agent | Action | Résultat |
|-------|-------|--------|----------|
""")

    # Log des améliorations
    if not IMPROVEMENTS_LOG.exists():
        IMPROVEMENTS_LOG.write_text(f"""# Améliorations Aura - {TODAY}

## Auto-améliorations effectuées

""")

    # Log des erreurs
    if not ERRORS_LOG.exists():
        ERRORS_LOG.write_text(f"""# Erreurs Aura - {TODAY}

| Heure | Agent | Erreur | Contexte |
|-------|-------|--------|----------|
""")

    # Log EBP App
    if not EBP_LOG.exists():
        EBP_LOG.write_text(f"""# Rapport EBP App - {TODAY}

## Builds
| Heure | Statut | Durée | Notes |
|-------|--------|-------|-------|

## Améliorations automatiques

## Erreurs détectées

""")

def log_action(agent: str, action: str, result: str, details: str = ""):
    """Log une action dans le rapport quotidien"""
    ensure_dirs()
    init_daily_files()

    timestamp = datetime.now().strftime("%H:%M:%S")

    # Ajouter à actions.md
    with open(ACTIONS_LOG, "a") as f:
        f.write(f"| {timestamp} | {agent} | {action} | {result} |\n")

    # Mettre à jour le compteur dans le résumé
    update_stats("actions")

    print(f"📝 Action loguée: {agent} - {action}")

def log_error(agent: str, error: str, context: str = ""):
    """Log une erreur"""
    ensure_dirs()
    init_daily_files()

    timestamp = datetime.now().strftime("%H:%M:%S")

    with open(ERRORS_LOG, "a") as f:
        f.write(f"| {timestamp} | {agent} | {error[:50]} | {context[:50]} |\n")

    update_stats("erreurs")
    print(f"❌ Erreur loguée: {agent} - {error[:50]}")

def log_improvement(description: str, files_changed: list = None):
    """Log une amélioration"""
    ensure_dirs()
    init_daily_files()

    timestamp = datetime.now().strftime("%H:%M:%S")

    with open(IMPROVEMENTS_LOG, "a") as f:
        f.write(f"### [{timestamp}] {description}\n")
        if files_changed:
            f.write("Fichiers modifiés:\n")
            for file in files_changed:
                f.write(f"- `{file}`\n")
        f.write("\n")

    update_stats("ameliorations")
    print(f"✨ Amélioration loguée: {description}")

def log_ebp_build(status: str, duration: str = "", notes: str = ""):
    """Log un build EBP"""
    ensure_dirs()
    init_daily_files()

    timestamp = datetime.now().strftime("%H:%M:%S")
    status_emoji = "✅" if status.lower() in ["ok", "success", "réussi"] else "❌"

    with open(EBP_LOG, "a") as f:
        # Trouver la section Builds et ajouter après le header du tableau
        content = f.read() if f.readable() else ""

    with open(EBP_LOG, "r") as f:
        content = f.read()

    # Insérer après le header du tableau des builds
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "| Heure | Statut | Durée | Notes |" in line:
            # La ligne suivante est le séparateur, insérer après
            if i + 2 < len(lines):
                lines.insert(i + 2, f"| {timestamp} | {status_emoji} {status} | {duration} | {notes} |")
            break

    with open(EBP_LOG, "w") as f:
        f.write("\n".join(lines))

    update_stats("builds")
    print(f"🔨 Build EBP logué: {status}")

def update_stats(stat_type: str):
    """Met à jour les statistiques dans le résumé"""
    if not DAILY_SUMMARY.exists():
        return

    content = DAILY_SUMMARY.read_text()

    # Mapping des stats
    stat_map = {
        "actions": "Actions effectuées",
        "erreurs": "Erreurs",
        "ameliorations": "Améliorations",
        "builds": "Builds EBP"
    }

    stat_name = stat_map.get(stat_type, stat_type)

    # Trouver et incrémenter la valeur
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if stat_name in line and "|" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                try:
                    current = int(parts[2].strip())
                    parts[2] = f" {current + 1} "
                    lines[i] = "|".join(parts)
                except ValueError:
                    pass
            break

    DAILY_SUMMARY.write_text("\n".join(lines))

def generate_summary():
    """Génère un résumé de la journée"""
    ensure_dirs()
    init_daily_files()

    # Compter les entrées dans chaque fichier
    actions = 0
    errors = 0

    if ACTIONS_LOG.exists():
        actions = len([l for l in ACTIONS_LOG.read_text().split("\n") if l.startswith("|") and "Heure" not in l and "---" not in l])

    if ERRORS_LOG.exists():
        errors = len([l for l in ERRORS_LOG.read_text().split("\n") if l.startswith("|") and "Heure" not in l and "---" not in l])

    summary = f"""
## Résumé généré à {datetime.now().strftime("%H:%M")}

- **Actions**: {actions}
- **Erreurs**: {errors}
- **Dernière mise à jour**: {datetime.now().strftime("%H:%M:%S")}

### Fichiers disponibles
- [Actions]({ACTIONS_LOG.name})
- [Améliorations]({IMPROVEMENTS_LOG.name})
- [Erreurs]({ERRORS_LOG.name})
- [EBP App]({EBP_LOG.name})
"""

    # Ajouter au résumé quotidien
    with open(DAILY_SUMMARY, "a") as f:
        f.write(summary)

    print(f"📊 Résumé généré: {DAILY_SUMMARY}")
    return summary

def list_reports(days: int = 7):
    """Liste les rapports des N derniers jours"""
    if not REPORTS_DIR.exists():
        print("Aucun rapport trouvé")
        return []

    reports = sorted(REPORTS_DIR.iterdir(), reverse=True)[:days]

    print(f"📁 Rapports disponibles ({len(reports)}):")
    for r in reports:
        if r.is_dir():
            files = list(r.glob("*.md"))
            print(f"  - {r.name}: {len(files)} fichiers")

    return reports

def main():
    """Point d'entrée principal"""
    import argparse

    parser = argparse.ArgumentParser(description="AURA Reporter - Gestion des rapports")
    parser.add_argument("command", choices=["init", "action", "error", "improve", "build", "summary", "list"],
                        help="Commande à exécuter")
    parser.add_argument("--agent", help="Nom de l'agent")
    parser.add_argument("--message", "-m", help="Message/description")
    parser.add_argument("--result", "-r", help="Résultat")
    parser.add_argument("--context", "-c", help="Contexte")
    parser.add_argument("--status", "-s", help="Statut (pour build)")
    parser.add_argument("--duration", "-d", help="Durée")
    parser.add_argument("--days", type=int, default=7, help="Nombre de jours (pour list)")

    args = parser.parse_args()

    if args.command == "init":
        init_daily_files()
        print(f"✅ Rapports initialisés pour {TODAY}")

    elif args.command == "action":
        if not args.agent or not args.message:
            print("❌ --agent et --message requis")
            return 1
        log_action(args.agent, args.message, args.result or "OK")

    elif args.command == "error":
        if not args.agent or not args.message:
            print("❌ --agent et --message requis")
            return 1
        log_error(args.agent, args.message, args.context or "")

    elif args.command == "improve":
        if not args.message:
            print("❌ --message requis")
            return 1
        log_improvement(args.message)

    elif args.command == "build":
        if not args.status:
            print("❌ --status requis")
            return 1
        log_ebp_build(args.status, args.duration or "", args.message or "")

    elif args.command == "summary":
        generate_summary()

    elif args.command == "list":
        list_reports(args.days)

    return 0

if __name__ == "__main__":
    sys.exit(main())
