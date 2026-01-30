#!/usr/bin/env python3
"""
AURA-OS Workflow Coordinator
Orchestre les agents en workflow avec rapports MD intermédiaires
Chaque agent lit les conclusions du précédent, le coordinateur agrège tout
Team: core
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict
import hashlib

WORKFLOWS_DIR = Path.home() / ".aura" / "workflows"
REPORTS_DIR = Path.home() / ".aura" / "workflow_reports"
TEMPLATES_FILE = Path.home() / ".aura" / "workflow_templates.json"

# Templates de workflows prédéfinis
DEFAULT_TEMPLATES = {
    "security_audit": {
        "name": "Audit Sécurité Complet",
        "description": "Audit sécurité + réseau + recommandations",
        "agents": [
            {"id": "security_auditor", "cmd": "python3 ~/.aura/agents/security_auditor.py audit", "role": "Audit de sécurité système"},
            {"id": "network_monitor", "cmd": "python3 ~/.aura/agents/network_monitor.py status", "role": "État du réseau"},
            {"id": "network_monitor_ports", "cmd": "python3 ~/.aura/agents/network_monitor.py ports", "role": "Analyse des ports"}
        ],
        "parallel": False
    },
    "system_health": {
        "name": "Santé Système Complète",
        "description": "Health check + processus + nettoyage recommandé",
        "agents": [
            {"id": "sys_health", "cmd": "python3 ~/.aura/agents/sys_health.py", "role": "État général du système"},
            {"id": "process_manager", "cmd": "python3 ~/.aura/agents/process_manager.py top", "role": "Processus consommateurs"},
            {"id": "system_cleaner", "cmd": "python3 ~/.aura/agents/system_cleaner.py scan", "role": "Scan nettoyage"}
        ],
        "parallel": True
    },
    "project_analysis": {
        "name": "Analyse Projet",
        "description": "Contexte projet + suggestions agents",
        "agents": [
            {"id": "project_context", "cmd": "python3 ~/.aura/agents/project_context.py analyze --verbose", "role": "Analyse du projet"},
            {"id": "project_suggest", "cmd": "python3 ~/.aura/agents/project_context.py suggest", "role": "Suggestions d'agents"}
        ],
        "parallel": False
    },
    "daily_maintenance": {
        "name": "Maintenance Quotidienne",
        "description": "Santé + sécurité rapide + nettoyage Claude",
        "agents": [
            {"id": "sys_health", "cmd": "python3 ~/.aura/agents/sys_health.py", "role": "Santé système"},
            {"id": "security_quick", "cmd": "python3 ~/.aura/agents/security_auditor.py quick", "role": "Audit rapide"},
            {"id": "claude_cleaner", "cmd": "python3 ~/.aura/agents/claude_cleaner.py clean", "role": "Nettoyage Claude"},
            {"id": "backup", "cmd": "python3 ~/.aura/agents/backup_manager.py run aura --dry-run", "role": "Vérification backup"}
        ],
        "parallel": False
    },
    "full_backup": {
        "name": "Backup Complet",
        "description": "Backup de tous les profils avec vérification",
        "agents": [
            {"id": "backup_all", "cmd": "python3 ~/.aura/agents/backup_manager.py run --all", "role": "Backup tous profils"},
            {"id": "backup_list", "cmd": "python3 ~/.aura/agents/backup_manager.py list", "role": "Liste des backups"}
        ],
        "parallel": False
    }
}

def load_templates() -> dict:
    """Charge les templates de workflows"""
    if TEMPLATES_FILE.exists():
        custom = json.loads(TEMPLATES_FILE.read_text())
        return {**DEFAULT_TEMPLATES, **custom}
    return DEFAULT_TEMPLATES.copy()

def save_templates(templates: dict):
    """Sauvegarde les templates personnalisés"""
    TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Ne sauvegarde que les templates custom (pas les defaults)
    custom = {k: v for k, v in templates.items() if k not in DEFAULT_TEMPLATES}
    TEMPLATES_FILE.write_text(json.dumps(custom, indent=2, ensure_ascii=False))

def generate_workflow_id() -> str:
    """Génère un ID unique pour un workflow"""
    return hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:8]

def create_report_header(workflow_name: str, workflow_id: str) -> str:
    """Crée l'en-tête du rapport MD"""
    return f"""# Rapport Workflow: {workflow_name}

**ID**: `{workflow_id}`
**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Généré par**: AURA Workflow Coordinator

---

"""

def create_agent_report(agent_id: str, role: str, output: str, status: str, duration: float) -> str:
    """Crée la section de rapport pour un agent"""
    status_icon = "✅" if status == "success" else "❌" if status == "error" else "⚠️"

    report = f"""
## {status_icon} Agent: `{agent_id}`

**Rôle**: {role}
**Status**: {status}
**Durée**: {duration:.2f}s

### Output

```
{output[:3000]}{'...(tronqué)' if len(output) > 3000 else ''}
```

### Conclusions

"""
    # Extrait les conclusions automatiquement (lignes avec Status, Total, etc.)
    conclusions = []
    for line in output.split('\n'):
        line_lower = line.lower()
        if any(kw in line_lower for kw in ['status:', 'total:', 'warning', 'error', 'critical', 'healthy', '✅', '❌', '⚠️', '🔴', '🟢', '🟡']):
            conclusions.append(f"- {line.strip()}")

    if conclusions:
        report += '\n'.join(conclusions[:10])
    else:
        report += "- Exécution terminée"

    report += "\n\n---\n"
    return report

def create_synthesis(results: list[Dict]) -> str:
    """Crée la synthèse finale du workflow"""
    success_count = sum(1 for r in results if r["status"] == "success")
    total_duration = sum(r["duration"] for r in results)

    synthesis = f"""
# 📊 Synthèse du Workflow

## Métriques

| Métrique | Valeur |
|----------|--------|
| Agents exécutés | {len(results)} |
| Succès | {success_count} |
| Échecs | {len(results) - success_count} |
| Durée totale | {total_duration:.2f}s |

## Actions Recommandées

"""

    # Analyse les outputs pour extraire des recommandations
    recommendations = []
    for result in results:
        output_lower = result["output"].lower()

        if "warning" in output_lower or "⚠️" in result["output"]:
            recommendations.append(f"- ⚠️ **{result['agent_id']}**: Vérifier les warnings détectés")

        if "error" in output_lower or "❌" in result["output"] or "failed" in output_lower:
            recommendations.append(f"- 🔴 **{result['agent_id']}**: Corriger les erreurs signalées")

        if "critical" in output_lower:
            recommendations.append(f"- 🚨 **{result['agent_id']}**: Action critique requise")

        if result["status"] != "success":
            recommendations.append(f"- 🔧 **{result['agent_id']}**: Investiguer l'échec d'exécution")

    if not recommendations:
        recommendations.append("- ✅ Aucune action urgente requise")
        recommendations.append("- 📝 Consulter les détails ci-dessus pour plus d'informations")

    synthesis += '\n'.join(recommendations[:15])

    synthesis += f"""

## Prochaines Étapes

1. Lire les conclusions de chaque agent ci-dessus
2. Adresser les actions recommandées par priorité
3. Relancer le workflow après corrections si nécessaire

---
*Rapport généré automatiquement par AURA Workflow Coordinator*
"""
    return synthesis

def run_agent(agent_config: dict, context_file: Path | None = None) -> dict:
    """Exécute un agent et retourne son résultat"""
    agent_id = agent_config["id"]
    cmd = agent_config["cmd"]
    role = agent_config.get("role", "Agent")

    print(f"  [>] Exécution: {agent_id}...")

    # Si un contexte existe, l'injecter (pour lecture par l'agent)
    env = os.environ.copy()
    if context_file and context_file.exists():
        env["AURA_WORKFLOW_CONTEXT"] = str(context_file)

    start_time = datetime.now()

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            env=env
        )

        duration = (datetime.now() - start_time).total_seconds()
        output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
        status = "success" if proc.returncode == 0 else "error"

    except subprocess.TimeoutExpired:
        duration = 300
        output = "TIMEOUT: L'agent n'a pas répondu dans les 5 minutes"
        status = "timeout"
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        output = f"EXCEPTION: {str(e)}"
        status = "error"

    print(f"      [{status}] {duration:.1f}s")

    return {
        "agent_id": agent_id,
        "role": role,
        "cmd": cmd,
        "output": output,
        "status": status,
        "duration": duration,
        "executed_at": datetime.now().isoformat()
    }

def run_workflow(template_name: str, parallel: bool | None = None,
                 output_dir: Path | None = None) -> dict:
    """Exécute un workflow complet"""
    templates = load_templates()

    if template_name not in templates:
        print(f"[-] Template inconnu: {template_name}")
        print(f"    Templates disponibles: {', '.join(templates.keys())}")
        return {"status": "error", "error": "Template not found"}

    template = templates[template_name]
    workflow_id = generate_workflow_id()
    use_parallel = parallel if parallel is not None else template.get("parallel", False)

    print(f"\n{'='*60}")
    print(f" Workflow: {template['name']}")
    print(f" ID: {workflow_id}")
    print(f" Mode: {'Parallèle' if use_parallel else 'Séquentiel'}")
    print(f"{'='*60}\n")

    # Prépare le répertoire de sortie
    if output_dir is None:
        output_dir = REPORTS_DIR / datetime.now().strftime("%Y-%m-%d") / workflow_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fichier de rapport principal
    report_file = output_dir / f"workflow_{template_name}_{workflow_id}.md"
    report_content = create_report_header(template["name"], workflow_id)

    # Fichier de contexte pour chaînage
    context_file = output_dir / "context.json"
    context_data = {
        "workflow_id": workflow_id,
        "template": template_name,
        "started_at": datetime.now().isoformat(),
        "previous_results": []
    }

    results = []

    if use_parallel:
        # Exécution parallèle avec ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(run_agent, agent): agent
                for agent in template["agents"]
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                report_content += create_agent_report(
                    result["agent_id"],
                    result["role"],
                    result["output"],
                    result["status"],
                    result["duration"]
                )
    else:
        # Exécution séquentielle avec chaînage de contexte
        for i, agent in enumerate(template["agents"]):
            # Sauvegarde le contexte pour cet agent
            context_data["current_step"] = i + 1
            context_data["total_steps"] = len(template["agents"])
            context_file.write_text(json.dumps(context_data, indent=2))

            result = run_agent(agent, context_file)
            results.append(result)

            # Ajoute au contexte pour le prochain agent
            context_data["previous_results"].append({
                "agent_id": result["agent_id"],
                "status": result["status"],
                "summary": result["output"][:500]
            })

            # Ajoute au rapport
            report_content += create_agent_report(
                result["agent_id"],
                result["role"],
                result["output"],
                result["status"],
                result["duration"]
            )

            # Crée un rapport intermédiaire pour cet agent
            agent_report_file = output_dir / f"step_{i+1}_{result['agent_id']}.md"
            agent_report_file.write_text(create_agent_report(
                result["agent_id"],
                result["role"],
                result["output"],
                result["status"],
                result["duration"]
            ))

    # Ajoute la synthèse
    report_content += create_synthesis(results)

    # Sauvegarde le rapport final
    report_file.write_text(report_content)

    # Sauvegarde les résultats JSON
    results_file = output_dir / "results.json"
    results_file.write_text(json.dumps({
        "workflow_id": workflow_id,
        "template": template_name,
        "started_at": context_data["started_at"],
        "completed_at": datetime.now().isoformat(),
        "results": results
    }, indent=2, ensure_ascii=False))

    # Résumé final
    success_count = sum(1 for r in results if r["status"] == "success")
    total_duration = sum(r["duration"] for r in results)

    print(f"\n{'='*60}")
    print(f" Workflow terminé!")
    print(f" Résultat: {success_count}/{len(results)} agents OK")
    print(f" Durée: {total_duration:.1f}s")
    print(f" Rapport: {report_file}")
    print(f"{'='*60}\n")

    return {
        "status": "success" if success_count == len(results) else "partial",
        "workflow_id": workflow_id,
        "success_count": success_count,
        "total_agents": len(results),
        "duration": total_duration,
        "report_file": str(report_file),
        "output_dir": str(output_dir)
    }

def list_templates():
    """Liste les templates disponibles"""
    templates = load_templates()

    print(f"\n{'='*60}")
    print(f" Templates de Workflow Disponibles")
    print(f"{'='*60}\n")

    for name, template in templates.items():
        # Ignorer les entrées metadata (commençant par _)
        if name.startswith("_"):
            continue
        if "agents" not in template:
            continue
        agents_count = len(template["agents"])
        mode = "⚡ Parallèle" if template.get("parallel") else "📝 Séquentiel"

        print(f" 📋 {name}")
        print(f"    {template['name']}")
        print(f"    {template['description']}")
        print(f"    {agents_count} agents | {mode}")
        print()

    print(f"Usage: python3 workflow_coordinator.py run <template_name>\n")

def list_reports(limit: int = 10):
    """Liste les rapports récents"""
    if not REPORTS_DIR.exists():
        print("[i] Aucun rapport trouvé")
        return

    reports = []
    for day_dir in sorted(REPORTS_DIR.iterdir(), reverse=True):
        if day_dir.is_dir():
            for workflow_dir in sorted(day_dir.iterdir(), reverse=True):
                if workflow_dir.is_dir():
                    report_files = list(workflow_dir.glob("workflow_*.md"))
                    if report_files:
                        reports.append({
                            "path": report_files[0],
                            "date": day_dir.name,
                            "id": workflow_dir.name
                        })

    if not reports:
        print("[i] Aucun rapport trouvé")
        return

    print(f"\n{'='*60}")
    print(f" Rapports Récents")
    print(f"{'='*60}\n")

    for report in reports[:limit]:
        print(f" {report['date']} | {report['id']} | {report['path'].name}")

    print(f"\n Pour lire un rapport: cat <chemin>\n")

def main():
    parser = argparse.ArgumentParser(
        description="AURA Workflow Coordinator - Orchestre les agents avec rapports MD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s run security_audit        # Audit sécurité complet
  %(prog)s run system_health         # Santé système
  %(prog)s run daily_maintenance     # Maintenance quotidienne
  %(prog)s list                      # Liste les templates
  %(prog)s reports                   # Liste les rapports récents
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commandes")

    # run
    run_parser = subparsers.add_parser("run", help="Exécuter un workflow")
    run_parser.add_argument("template", help="Nom du template")
    run_parser.add_argument("--parallel", "-p", action="store_true", help="Forcer mode parallèle")
    run_parser.add_argument("--sequential", "-s", action="store_true", help="Forcer mode séquentiel")
    run_parser.add_argument("--output", "-o", help="Répertoire de sortie")

    # list
    subparsers.add_parser("list", help="Lister les templates")

    # reports
    reports_parser = subparsers.add_parser("reports", help="Lister les rapports")
    reports_parser.add_argument("--limit", "-n", type=int, default=10)

    # read (raccourci pour lire un rapport)
    read_parser = subparsers.add_parser("read", help="Lire un rapport")
    read_parser.add_argument("report_id", help="ID du workflow ou chemin")

    args = parser.parse_args()

    if args.command == "run":
        parallel = None
        if args.parallel:
            parallel = True
        elif args.sequential:
            parallel = False

        output_dir = Path(args.output) if args.output else None
        result = run_workflow(args.template, parallel, output_dir)

        # Notification vocale
        if result["status"] == "success":
            msg = f"Workflow terminé avec succès. {result['success_count']} agents exécutés."
        else:
            msg = f"Workflow terminé. {result['success_count']} sur {result['total_agents']} agents OK."

        subprocess.run([
            "python3", str(Path.home() / ".aura/agents/voice_speak.py"),
            msg
        ], capture_output=True)

    elif args.command == "list":
        list_templates()

    elif args.command == "reports":
        list_reports(args.limit)

    elif args.command == "read":
        # Cherche le rapport
        report_path = None
        if Path(args.report_id).exists():
            report_path = Path(args.report_id)
        else:
            for day_dir in REPORTS_DIR.iterdir():
                if day_dir.is_dir():
                    candidate = day_dir / args.report_id
                    if candidate.exists():
                        reports = list(candidate.glob("workflow_*.md"))
                        if reports:
                            report_path = reports[0]
                            break

        if report_path:
            print(report_path.read_text())
        else:
            print(f"[-] Rapport non trouvé: {args.report_id}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
