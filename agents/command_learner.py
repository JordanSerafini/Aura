#!/usr/bin/env python3
"""
AURA Command Learner - Apprend les patterns de commandes de l'utilisateur
"""

import json
import os
from pathlib import Path
from collections import Counter
from datetime import datetime

HISTORY_FILE = Path.home() / ".aura" / "command_history.log"
PATTERNS_FILE = Path.home() / ".aura" / "learned_patterns.json"

def load_patterns():
    if PATTERNS_FILE.exists():
        with open(PATTERNS_FILE) as f:
            return json.load(f)
    return {"commands": [], "frequencies": {}, "last_updated": None}

def save_patterns(patterns):
    patterns["last_updated"] = datetime.now().isoformat()
    with open(PATTERNS_FILE, 'w') as f:
        json.dump(patterns, f, indent=2)

def analyze_history():
    """Analyse l'historique bash pour trouver les patterns"""
    patterns = load_patterns()
    
    # Lire l'historique bash
    bash_history = Path.home() / ".bash_history"
    if bash_history.exists():
        with open(bash_history, errors='ignore') as f:
            commands = [line.strip() for line in f if line.strip()]
        
        # Compter les fréquences
        freq = Counter(commands)
        top_commands = freq.most_common(50)
        
        patterns["frequencies"] = {cmd: count for cmd, count in top_commands}
        patterns["total_commands"] = len(commands)
        
        # Détecter les patterns de projets
        project_dirs = [cmd.split()[-1] for cmd in commands if cmd.startswith("cd ") and "/" in cmd]
        patterns["frequent_dirs"] = dict(Counter(project_dirs).most_common(10))
        
        save_patterns(patterns)
        return patterns
    
    return None

def suggest_alias(command):
    """Suggère un alias pour une commande fréquente"""
    patterns = load_patterns()
    freq = patterns.get("frequencies", {})
    
    if command in freq and freq[command] > 10:
        short_name = command.split()[0][:4]
        return f"alias {short_name}='{command}'"
    return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AURA Command Learner")
    parser.add_argument("action", choices=["analyze", "show", "suggest"])
    args = parser.parse_args()
    
    if args.action == "analyze":
        result = analyze_history()
        if result:
            print(f"✅ Analysé {result.get('total_commands', 0)} commandes")
            print(f"Top 5 commandes:")
            for cmd, count in list(result.get('frequencies', {}).items())[:5]:
                print(f"  {count:4d}x  {cmd[:60]}")
    
    elif args.action == "show":
        patterns = load_patterns()
        print(json.dumps(patterns, indent=2))
    
    elif args.action == "suggest":
        patterns = load_patterns()
        freq = patterns.get("frequencies", {})
        print("Suggestions d'aliases pour commandes fréquentes:")
        for cmd, count in list(freq.items())[:10]:
            if count > 5 and len(cmd) > 10:
                words = cmd.split()
                if words:
                    alias_name = words[0][:3] + str(len(words))
                    print(f"  alias {alias_name}='{cmd}'")

if __name__ == "__main__":
    main()
