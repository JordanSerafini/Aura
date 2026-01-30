#!/usr/bin/env python3
"""
AURA Token Optimizer v1.0 - Monitoring et optimisation des tokens
Suit l'usage et recommande des optimisations.

Team: core (monitoring)

Stratégies d'optimisation:
1. Déléguer aux subagents (haiku pour tâches simples)
2. Paralléliser les tool calls
3. Compresser le contexte
4. Cache des résultats fréquents
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


OPTIMIZER_DIR = Path.home() / ".aura" / "token_stats"
OPTIMIZER_DIR.mkdir(parents=True, exist_ok=True)

SESSION_LOG = OPTIMIZER_DIR / "sessions.jsonl"
TIPS_FILE = OPTIMIZER_DIR / "optimization_tips.json"


# Commandes Claude Code pour monitoring
CLAUDE_CODE_COMMANDS = {
    "/usage": "Affiche l'usage des tokens de la session",
    "/context": "Montre l'utilisation du contexte",
    "/cost": "Affiche le coût estimé",
    "ccusage": "CLI npm pour historique détaillé",
}


# Tips d'optimisation pour Claude Code
OPTIMIZATION_TIPS = {
    "delegate_simple_tasks": {
        "description": "Utiliser haiku pour recherches et explorations simples",
        "example": "Task tool avec model='haiku' pour Explore, Grep simple",
        "savings": "60-80% de tokens sur tâches simples"
    },
    "parallel_tool_calls": {
        "description": "Grouper les appels d'outils indépendants",
        "example": "Lire 3 fichiers en 1 appel au lieu de 3 tours",
        "savings": "Réduit les tours API de 50%+"
    },
    "concise_responses": {
        "description": "Réponses courtes et factuelles",
        "example": "✅ au lieu de 'J'ai réussi à compléter la tâche avec succès'",
        "savings": "30-50% de tokens output"
    },
    "use_agents_not_bash": {
        "description": "Agents AURA au lieu de bash brut",
        "example": "sys_health.py au lieu de top + free + df",
        "savings": "Output plus structuré, moins de parsing"
    },
    "smart_file_reading": {
        "description": "Lire seulement les parties nécessaires des fichiers",
        "example": "offset/limit pour gros fichiers",
        "savings": "90%+ sur gros fichiers"
    },
    "context_compression": {
        "description": "Résumer le contexte périodiquement",
        "example": "Archiver les détails, garder les décisions",
        "savings": "Évite épuisement du contexte"
    },
    "cache_frequent_results": {
        "description": "Cacher les résultats de commandes fréquentes",
        "example": "sys_health cache 5min, manifest cache session",
        "savings": "Évite répétitions"
    }
}


def get_ccusage_stats() -> dict | None:
    """Récupère les stats via ccusage."""
    try:
        result = subprocess.run(
            ["ccusage", "--json", "--today"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass

    # Fallback: parser la sortie standard
    try:
        result = subprocess.run(
            ["ccusage", "--today"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return {"raw_output": result.stdout}
    except Exception:
        pass

    return None


def get_context_estimate() -> dict:
    """Estime l'utilisation du contexte actuel."""
    # Heuristiques basées sur les fichiers de session Claude Code
    claude_dir = Path.home() / ".claude"
    stats_cache = claude_dir / "statsig" / "statsig_cache.json"

    context_info = {
        "estimated": True,
        "warning": None
    }

    # Chercher le fichier de session actif
    projects_dir = claude_dir / "projects"
    if projects_dir.exists():
        jsonl_files = list(projects_dir.rglob("*.jsonl"))
        if jsonl_files:
            # Le plus récent
            latest = max(jsonl_files, key=lambda f: f.stat().st_mtime)
            size_kb = latest.stat().st_size / 1024
            context_info["session_file"] = str(latest.name)
            context_info["session_size_kb"] = round(size_kb, 1)

            # Estimation grossière: ~4 chars/token, 200k context
            estimated_tokens = (latest.stat().st_size / 4)
            context_pct = (estimated_tokens / 200000) * 100
            context_info["estimated_context_pct"] = round(min(context_pct, 100), 1)

            if context_pct > 80:
                context_info["warning"] = "Context > 80%, consider summarizing"
            elif context_pct > 60:
                context_info["warning"] = "Context > 60%, monitor usage"

    return context_info


def log_session_stats(stats: dict) -> None:
    """Log les stats de session."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        **stats
    }
    with open(SESSION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def get_recommendations(context_info: dict) -> list[str]:
    """Génère des recommandations basées sur l'état actuel."""
    recs = []

    pct = context_info.get("estimated_context_pct", 0)
    if pct > 70:
        recs.append("🔴 HIGH: Contexte élevé - déléguer plus aux subagents haiku")
        recs.append("🔴 HIGH: Résumer les résultats intermédiaires")

    if pct > 50:
        recs.append("🟡 MED: Utiliser offset/limit pour les gros fichiers")
        recs.append("🟡 MED: Paralléliser les tool calls indépendants")

    recs.append("🟢 TIP: Utiliser Task(model='haiku') pour explorations")
    recs.append("🟢 TIP: Réponses vocales courtes (1-2 phrases)")

    return recs


def print_status() -> None:
    """Affiche le statut d'optimisation."""
    print("\n" + "=" * 60)
    print("  AURA Token Optimizer - Status")
    print("=" * 60)

    # ccusage
    ccusage = get_ccusage_stats()
    if ccusage:
        print("\n  📊 ccusage (today):")
        if "raw_output" in ccusage:
            # Afficher les premières lignes
            lines = ccusage["raw_output"].split("\n")[:10]
            for line in lines:
                if line.strip():
                    print(f"    {line}")

    # Context estimate
    context = get_context_estimate()
    print("\n  📈 Context estimate:")
    print(f"    Session size: {context.get('session_size_kb', '?')} KB")
    print(f"    Estimated usage: {context.get('estimated_context_pct', '?')}%")
    if context.get("warning"):
        print(f"    ⚠️ {context['warning']}")

    # Recommendations
    print("\n  💡 Recommendations:")
    recs = get_recommendations(context)
    for rec in recs[:5]:
        print(f"    {rec}")

    print("\n" + "=" * 60 + "\n")


def print_tips() -> None:
    """Affiche tous les tips d'optimisation."""
    print("\n" + "=" * 60)
    print("  AURA Token Optimization Tips")
    print("=" * 60 + "\n")

    for name, tip in OPTIMIZATION_TIPS.items():
        print(f"  📌 {name}")
        print(f"     {tip['description']}")
        print(f"     Example: {tip['example']}")
        print(f"     Savings: {tip['savings']}")
        print()

    print("=" * 60 + "\n")


def get_statusline() -> str:
    """Retourne une ligne de statut compacte pour statusline."""
    context = get_context_estimate()
    pct = context.get("estimated_context_pct", 0)

    if pct > 80:
        indicator = "🔴"
    elif pct > 60:
        indicator = "🟡"
    else:
        indicator = "🟢"

    return f"{indicator} CTX:{pct:.0f}%"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AURA Token Optimizer")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Affiche le statut")
    subparsers.add_parser("tips", help="Affiche les tips d'optimisation")
    subparsers.add_parser("statusline", help="Ligne compacte pour statusline")
    subparsers.add_parser("ccusage", help="Stats ccusage")
    subparsers.add_parser("context", help="Estimation du contexte")

    args = parser.parse_args()

    if args.command == "status":
        print_status()

    elif args.command == "tips":
        print_tips()

    elif args.command == "statusline":
        print(get_statusline())

    elif args.command == "ccusage":
        stats = get_ccusage_stats()
        if stats:
            if "raw_output" in stats:
                print(stats["raw_output"])
            else:
                print(json.dumps(stats, indent=2))
        else:
            print("ccusage not available")

    elif args.command == "context":
        context = get_context_estimate()
        print(json.dumps(context, indent=2))

    else:
        # Default: status
        print_status()


if __name__ == "__main__":
    main()
