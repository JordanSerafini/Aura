#!/usr/bin/env python3
"""
AURA-OS Agent: Agent Factory
Team: Core
Description: Meta-agent qui crée d'autres agents en background
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

AURA_DIR = Path.home() / ".aura"
AGENTS_DIR = AURA_DIR / "agents"
MANIFEST_FILE = AURA_DIR / "agents_manifest.json"

# Templates d'agents par type
TEMPLATES = {
    "scraper": '''#!/usr/bin/env python3
"""
AURA-OS Agent: {name}
Team: {team}
Description: {description}
"""
import argparse
import requests
from bs4 import BeautifulSoup

def main():
    parser = argparse.ArgumentParser(description="{description}")
    parser.add_argument("url", help="URL à scraper")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    resp = requests.get(args.url, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")
    # TODO: Implémenter la logique de scraping
    print(f"✅ Scraped: {{args.url}}")

if __name__ == "__main__":
    main()
''',

    "monitor": '''#!/usr/bin/env python3
"""
AURA-OS Agent: {name}
Team: {team}
Description: {description}
"""
import argparse
import time
import subprocess

def main():
    parser = argparse.ArgumentParser(description="{description}")
    parser.add_argument("--interval", type=int, default=5, help="Intervalle en secondes")
    parser.add_argument("--once", action="store_true", help="Une seule exécution")
    args = parser.parse_args()

    while True:
        # TODO: Implémenter la logique de monitoring
        print(f"📊 Monitoring... {{time.strftime('%H:%M:%S')}}")
        if args.once:
            break
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
''',

    "utility": '''#!/usr/bin/env python3
"""
AURA-OS Agent: {name}
Team: {team}
Description: {description}
"""
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="{description}")
    parser.add_argument("command", choices=["run", "status", "help"])
    args = parser.parse_args()

    if args.command == "run":
        # TODO: Implémenter la logique
        print("✅ Exécuté")
    elif args.command == "status":
        print("📊 Status: OK")

if __name__ == "__main__":
    main()
''',

    "empty": '''#!/usr/bin/env python3
"""
AURA-OS Agent: {name}
Team: {team}
Description: {description}
"""
import argparse

def main():
    parser = argparse.ArgumentParser(description="{description}")
    # TODO: Ajouter les arguments
    args = parser.parse_args()
    # TODO: Implémenter
    print("✅ Agent {name} exécuté")

if __name__ == "__main__":
    main()
'''
}


def load_manifest():
    """Charge le manifest des agents"""
    if MANIFEST_FILE.exists():
        return json.loads(MANIFEST_FILE.read_text())
    return {"agents": []}


def save_manifest(manifest):
    """Sauvegarde le manifest"""
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def create_agent(name: str, team: str, description: str, template: str = "empty"):
    """Crée un nouvel agent"""
    # Générer le nom du fichier
    filename = name.lower().replace(" ", "_").replace("-", "_") + ".py"
    filepath = AGENTS_DIR / filename

    if filepath.exists():
        print(f"⚠️ Agent {filename} existe déjà")
        return None

    # Générer le code depuis le template
    code = TEMPLATES.get(template, TEMPLATES["empty"]).format(
        name=name,
        team=team,
        description=description
    )

    # Écrire le fichier
    filepath.write_text(code)
    filepath.chmod(0o755)

    # Ajouter au manifest
    manifest = load_manifest()
    agent_entry = {
        "id": name.lower().replace(" ", "_"),
        "name": name,
        "team": team,
        "script": filename,
        "description": description,
        "created": datetime.now().isoformat(),
        "arguments": []
    }
    manifest["agents"].append(agent_entry)
    save_manifest(manifest)

    return filepath


def list_templates():
    """Liste les templates disponibles"""
    print("\n📋 Templates disponibles:")
    for name, code in TEMPLATES.items():
        lines = len(code.split('\n'))
        print(f"  • {name} ({lines} lignes)")


def create_batch(specs_file: str):
    """Crée plusieurs agents depuis un fichier JSON"""
    specs = json.loads(Path(specs_file).read_text())
    created = []

    for spec in specs.get("agents", []):
        result = create_agent(
            name=spec["name"],
            team=spec["team"],
            description=spec["description"],
            template=spec.get("template", "empty")
        )
        if result:
            created.append(result)
            print(f"✅ Créé: {result.name}")

    return created


def main():
    parser = argparse.ArgumentParser(description="Factory de création d'agents Aura-OS")
    parser.add_argument("command", choices=["create", "batch", "templates", "list"])
    parser.add_argument("--name", "-n", help="Nom de l'agent")
    parser.add_argument("--team", "-t", choices=["core", "cyber", "pc-admin", "info-data", "vocal-ui"],
                       help="Équipe de l'agent")
    parser.add_argument("--desc", "-d", help="Description de l'agent")
    parser.add_argument("--template", choices=list(TEMPLATES.keys()), default="empty",
                       help="Template à utiliser")
    parser.add_argument("--file", "-f", help="Fichier JSON pour batch create")

    args = parser.parse_args()

    if args.command == "templates":
        list_templates()

    elif args.command == "list":
        manifest = load_manifest()
        print(f"\n📦 {len(manifest.get('agents', []))} agents enregistrés:")
        for agent in manifest.get("agents", []):
            print(f"  • [{agent.get('team', '?')}] {agent.get('name', '?')}")

    elif args.command == "create":
        if not all([args.name, args.team, args.desc]):
            print("❌ Requis: --name, --team, --desc")
            sys.exit(1)
        result = create_agent(args.name, args.team, args.desc, args.template)
        if result:
            print(f"✅ Agent créé: {result}")

    elif args.command == "batch":
        if not args.file:
            print("❌ Requis: --file")
            sys.exit(1)
        create_batch(args.file)


if __name__ == "__main__":
    main()
