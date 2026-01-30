#!/usr/bin/env python3
"""
AURA Agent: Thought Processor (Brain Dump)
Team: Core
Description: Transforme des pensées en vrac en plan d'action structuré MD

Usage:
    python3 thought_processor.py "Tes pensées ici..."
    python3 thought_processor.py --interactive
    python3 thought_processor.py --file input.txt
    cat pensees.txt | python3 thought_processor.py --stdin
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Chemins
AURA_DIR = Path.home() / ".aura"
OUTPUT_DIR = AURA_DIR / "brain_dumps"
MANIFEST_PATH = AURA_DIR / "agents_manifest.json"
LOGGER = AURA_DIR / "agents" / "logger_master.py"

def log(status: str, message: str, details: str = ""):
    """Log via logger_master"""
    import subprocess
    cmd = [
        "python3", str(LOGGER),
        "--team", "core",
        "--agent", "thought_processor",
        "--status", status,
        "--message", message
    ]
    if details:
        cmd.extend(["--details", details])
    subprocess.run(cmd, capture_output=True)

def load_manifest() -> dict:
    """Charge le manifest des agents pour connaître les capacités disponibles"""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, 'r') as f:
            return json.load(f)
    return {"agents": []}

def get_agent_capabilities() -> str:
    """Retourne une description des agents disponibles"""
    manifest = load_manifest()
    capabilities = []
    for agent in manifest.get("agents", []):
        capabilities.append(f"- {agent['name']}: {agent.get('description', 'N/A')}")
    return "\n".join(capabilities) if capabilities else "Aucun agent documenté"

def structure_thoughts(raw_thoughts: str) -> dict:
    """
    Analyse les pensées et extrait la structure.
    Retourne un dict avec contexte, objectifs, actions, notes.
    """
    lines = [l.strip() for l in raw_thoughts.split('\n') if l.strip()]

    result = {
        "raw_input": raw_thoughts,
        "timestamp": datetime.now().isoformat(),
        "context": [],
        "objectives": [],
        "actions": [],
        "notes": [],
        "keywords": [],
        "suggested_agents": []
    }

    # Mots-clés d'action
    action_keywords = {
        "installer": "app_installer",
        "install": "app_installer",
        "nettoyer": "system_cleaner",
        "clean": "system_cleaner",
        "supprimer": "system_cleaner",
        "delete": "system_cleaner",
        "vérifier": "sys_health",
        "check": "sys_health",
        "monitor": "sys_health",
        "surveiller": "network_monitor",
        "réseau": "network_monitor",
        "network": "network_monitor",
        "sécurité": "security_auditor",
        "security": "security_auditor",
        "audit": "security_auditor",
        "processus": "process_manager",
        "process": "process_manager",
        "kill": "process_manager",
        "tuer": "process_manager",
        "fenêtre": "plasma_controller",
        "window": "plasma_controller",
        "news": "tech_watcher",
        "veille": "tech_watcher",
        "dire": "voice_speak",
        "parler": "voice_speak",
        "speak": "voice_speak",
        "créer agent": "agent_factory",
        "nouvel agent": "agent_factory",
    }

    # Indicateurs de structure
    action_indicators = ["faire", "do", "exécuter", "run", "lancer", "créer", "create",
                         "installer", "install", "supprimer", "delete", "vérifier", "check",
                         "je veux", "il faut", "on doit", "besoin de", "need to"]
    objective_indicators = ["objectif", "goal", "but", "pour", "afin de", "so that",
                           "le but", "l'idée", "je voudrais", "I want"]
    context_indicators = ["parce que", "because", "car", "since", "étant donné",
                         "given", "contexte", "context", "situation"]

    for line in lines:
        line_lower = line.lower()

        # Détecter les agents suggérés
        for keyword, agent in action_keywords.items():
            if keyword in line_lower and agent not in result["suggested_agents"]:
                result["suggested_agents"].append(agent)
                result["keywords"].append(keyword)

        # Classifier la ligne
        if any(ind in line_lower for ind in action_indicators):
            result["actions"].append(line)
        elif any(ind in line_lower for ind in objective_indicators):
            result["objectives"].append(line)
        elif any(ind in line_lower for ind in context_indicators):
            result["context"].append(line)
        else:
            # Par défaut, c'est une note ou contexte
            if len(line) > 50:
                result["context"].append(line)
            else:
                result["notes"].append(line)

    # Si aucune action détectée, tout mettre en notes pour analyse manuelle
    if not result["actions"] and not result["objectives"]:
        result["notes"] = lines

    return result

def generate_markdown(structured: dict) -> str:
    """Génère le fichier Markdown structuré"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    md = f"""# Brain Dump - {timestamp}

> Généré par `thought_processor.py` | AURA-OS

---

## Entrée brute
```
{structured['raw_input']}
```

---

## Analyse structurée

### Contexte
"""

    if structured["context"]:
        for ctx in structured["context"]:
            md += f"- {ctx}\n"
    else:
        md += "_Aucun contexte explicite détecté_\n"

    md += "\n### Objectifs identifiés\n"
    if structured["objectives"]:
        for i, obj in enumerate(structured["objectives"], 1):
            md += f"{i}. {obj}\n"
    else:
        md += "_Aucun objectif explicite détecté_\n"

    md += "\n### Actions à exécuter\n"
    if structured["actions"]:
        for action in structured["actions"]:
            md += f"- [ ] {action}\n"
    else:
        md += "_Aucune action explicite détectée_\n"

    md += "\n### Agents suggérés\n"
    if structured["suggested_agents"]:
        md += "| Agent | Raison |\n|-------|--------|\n"
        for i, agent in enumerate(structured["suggested_agents"]):
            keyword = structured["keywords"][i] if i < len(structured["keywords"]) else "?"
            md += f"| `{agent}` | Mot-clé: \"{keyword}\" |\n"
    else:
        md += "_Aucun agent spécifique suggéré_\n"

    md += "\n### Notes additionnelles\n"
    if structured["notes"]:
        for note in structured["notes"]:
            md += f"- {note}\n"
    else:
        md += "_Aucune note_\n"

    md += f"""
---

## Métadonnées
- **Timestamp**: {structured['timestamp']}
- **Mots-clés détectés**: {', '.join(structured['keywords']) if structured['keywords'] else 'Aucun'}
- **Format**: Compatible AURA agents

---

## Instructions pour agents
Pour exécuter ce plan, les agents peuvent parser ce fichier et extraire :
- Les actions `- [ ]` comme tâches à faire
- Les agents suggérés pour le routage
- Le contexte pour comprendre l'intention

*Fichier généré automatiquement par AURA thought_processor*
"""

    return md

def save_output(content: str, filename: str = None) -> Path:
    """Sauvegarde le MD dans brain_dumps/"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"brain_dump_{timestamp}.md"

    output_path = OUTPUT_DIR / filename
    with open(output_path, 'w') as f:
        f.write(content)

    return output_path

def interactive_mode():
    """Mode interactif pour saisir plusieurs pensées"""
    print("🧠 Mode Brain Dump interactif")
    print("   Tape tes pensées (ligne vide + 'FIN' pour terminer)")
    print("-" * 50)

    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == "FIN":
                break
            lines.append(line)
        except EOFError:
            break

    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(
        description="Transforme des pensées en vrac en plan d'action structuré"
    )
    parser.add_argument("thoughts", nargs="*", help="Pensées à traiter")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Mode interactif multi-lignes")
    parser.add_argument("--file", "-f", type=str, help="Lire depuis un fichier")
    parser.add_argument("--stdin", action="store_true", help="Lire depuis stdin")
    parser.add_argument("--output", "-o", type=str, help="Nom du fichier de sortie")
    parser.add_argument("--quiet", "-q", action="store_true", help="Sortie minimale")

    args = parser.parse_args()

    # Récupérer les pensées
    raw_thoughts = ""

    if args.interactive:
        raw_thoughts = interactive_mode()
    elif args.file:
        with open(args.file, 'r') as f:
            raw_thoughts = f.read()
    elif args.stdin:
        raw_thoughts = sys.stdin.read()
    elif args.thoughts:
        raw_thoughts = " ".join(args.thoughts)
    elif not sys.stdin.isatty():
        raw_thoughts = sys.stdin.read()
    else:
        print("❌ Aucune entrée fournie. Utilise --help pour l'aide.")
        sys.exit(1)

    if not raw_thoughts.strip():
        print("❌ Entrée vide")
        sys.exit(1)

    # Traitement
    structured = structure_thoughts(raw_thoughts)
    markdown = generate_markdown(structured)
    output_path = save_output(markdown, args.output)

    # Log
    log("success", "Brain dump traité", f"Output: {output_path}")

    # Sortie
    if args.quiet:
        print(str(output_path))
    else:
        print(f"✅ Brain dump structuré créé !")
        print(f"📄 Fichier: {output_path}")
        print(f"🎯 Objectifs détectés: {len(structured['objectives'])}")
        print(f"⚡ Actions détectées: {len(structured['actions'])}")
        print(f"🤖 Agents suggérés: {', '.join(structured['suggested_agents']) or 'Aucun'}")

    return str(output_path)

if __name__ == "__main__":
    main()
