#!/usr/bin/env python3
"""
AURA-OS System Scheduler Agent
Planification intelligente de tâches avec support cron-like et événements
Team: core
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
import hashlib

SCHEDULE_FILE = Path.home() / ".aura" / "schedules.json"
HISTORY_FILE = Path.home() / ".aura" / "schedule_history.json"

def load_schedules() -> dict:
    """Charge les tâches planifiées"""
    if SCHEDULE_FILE.exists():
        return json.loads(SCHEDULE_FILE.read_text())
    return {"tasks": [], "version": "1.0.0"}

def save_schedules(data: dict):
    """Sauvegarde les tâches planifiées"""
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def load_history() -> list:
    """Charge l'historique d'exécution"""
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []

def save_history(history: list):
    """Sauvegarde l'historique (garde les 100 derniers)"""
    HISTORY_FILE.write_text(json.dumps(history[-100:], indent=2, ensure_ascii=False))

def generate_task_id(name: str) -> str:
    """Génère un ID unique pour une tâche"""
    return hashlib.md5(f"{name}{datetime.now().isoformat()}".encode()).hexdigest()[:8]

def parse_interval(interval: str) -> timedelta:
    """Parse un intervalle humain (5m, 1h, 2d, 1w)"""
    units = {'m': 'minutes', 'h': 'hours', 'd': 'days', 'w': 'weeks'}
    value = int(interval[:-1])
    unit = interval[-1].lower()
    if unit not in units:
        raise ValueError(f"Unité inconnue: {unit}. Utilisez m/h/d/w")
    return timedelta(**{units[unit]: value})

def add_task(name: str, command: str, interval: str, enabled: bool = True) -> dict:
    """Ajoute une tâche planifiée"""
    data = load_schedules()

    # Vérifie si la tâche existe déjà
    for task in data["tasks"]:
        if task["name"] == name:
            print(f"[!] Tâche '{name}' existe déjà. Utilisez 'update' pour modifier.")
            return task

    task = {
        "id": generate_task_id(name),
        "name": name,
        "command": command,
        "interval": interval,
        "enabled": enabled,
        "created": datetime.now().isoformat(),
        "last_run": None,
        "next_run": datetime.now().isoformat(),
        "run_count": 0,
        "last_status": None
    }

    data["tasks"].append(task)
    save_schedules(data)
    print(f"[+] Tâche '{name}' ajoutée (interval: {interval})")
    return task

def remove_task(task_id: str) -> bool:
    """Supprime une tâche"""
    data = load_schedules()
    original_len = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id and t["name"] != task_id]

    if len(data["tasks"]) < original_len:
        save_schedules(data)
        print(f"[+] Tâche supprimée")
        return True
    print(f"[-] Tâche non trouvée: {task_id}")
    return False

def toggle_task(task_id: str, enabled: bool | None = None) -> bool:
    """Active/désactive une tâche"""
    data = load_schedules()
    for task in data["tasks"]:
        if task["id"] == task_id or task["name"] == task_id:
            task["enabled"] = enabled if enabled is not None else not task["enabled"]
            save_schedules(data)
            status = "activée" if task["enabled"] else "désactivée"
            print(f"[+] Tâche '{task['name']}' {status}")
            return True
    print(f"[-] Tâche non trouvée: {task_id}")
    return False

def run_task(task: dict) -> dict:
    """Exécute une tâche"""
    start_time = datetime.now()
    result = {
        "task_id": task["id"],
        "task_name": task["name"],
        "started": start_time.isoformat(),
        "command": task["command"]
    }

    try:
        proc = subprocess.run(
            task["command"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        result["exit_code"] = proc.returncode
        result["stdout"] = proc.stdout[:500] if proc.stdout else ""
        result["stderr"] = proc.stderr[:500] if proc.stderr else ""
        result["status"] = "success" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["exit_code"] = -1
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["exit_code"] = -1

    result["duration"] = (datetime.now() - start_time).total_seconds()
    result["ended"] = datetime.now().isoformat()

    # Enregistre dans l'historique
    history = load_history()
    history.append(result)
    save_history(history)

    return result

def check_and_run() -> list:
    """Vérifie et exécute les tâches dues"""
    data = load_schedules()
    now = datetime.now()
    executed = []

    for task in data["tasks"]:
        if not task["enabled"]:
            continue

        next_run = datetime.fromisoformat(task["next_run"])
        if now >= next_run:
            print(f"[>] Exécution de '{task['name']}'...")
            result = run_task(task)
            executed.append(result)

            # Mise à jour de la tâche
            task["last_run"] = now.isoformat()
            task["run_count"] += 1
            task["last_status"] = result["status"]

            # Calcule la prochaine exécution
            interval = parse_interval(task["interval"])
            task["next_run"] = (now + interval).isoformat()

    save_schedules(data)
    return executed

def list_tasks(show_all: bool = False) -> list:
    """Liste les tâches planifiées"""
    data = load_schedules()
    tasks = data["tasks"]

    if not tasks:
        print("[i] Aucune tâche planifiée")
        return []

    print(f"\n{'='*60}")
    print(f"{'ID':<10} {'Nom':<20} {'Interval':<10} {'Status':<10} {'Prochain':<20}")
    print(f"{'='*60}")

    for task in tasks:
        if not show_all and not task["enabled"]:
            continue

        status = "ON" if task["enabled"] else "OFF"
        next_run = task["next_run"][:16] if task["next_run"] else "N/A"
        last_status = task.get("last_status", "-")

        print(f"{task['id']:<10} {task['name']:<20} {task['interval']:<10} {status:<10} {next_run}")

    print(f"{'='*60}\n")
    return tasks

def show_history(limit: int = 10) -> list:
    """Affiche l'historique d'exécution"""
    history = load_history()
    recent = history[-limit:]

    if not recent:
        print("[i] Aucun historique")
        return []

    print(f"\n{'='*70}")
    print(f"{'Tâche':<20} {'Status':<10} {'Durée':<10} {'Date':<30}")
    print(f"{'='*70}")

    for entry in reversed(recent):
        name = entry.get("task_name", "?")[:18]
        status = entry.get("status", "?")
        duration = f"{entry.get('duration', 0):.1f}s"
        date = entry.get("started", "?")[:19]

        print(f"{name:<20} {status:<10} {duration:<10} {date}")

    print(f"{'='*70}\n")
    return recent

def daemon_mode(check_interval: int = 60):
    """Mode daemon - vérifie les tâches périodiquement"""
    print(f"[*] Scheduler daemon démarré (check every {check_interval}s)")
    print("[*] Ctrl+C pour arrêter\n")

    import time
    try:
        while True:
            executed = check_and_run()
            if executed:
                for e in executed:
                    status_icon = "" if e["status"] == "success" else ""
                    print(f"  {status_icon} {e['task_name']}: {e['status']} ({e['duration']:.1f}s)")
            time.sleep(check_interval)
    except KeyboardInterrupt:
        print("\n[*] Scheduler arrêté")

def main():
    parser = argparse.ArgumentParser(
        description="AURA System Scheduler - Planification intelligente",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s add "backup" "python3 ~/.aura/agents/backup_manager.py run" --interval 1d
  %(prog)s add "health-check" "python3 ~/.aura/agents/sys_health.py" --interval 30m
  %(prog)s list
  %(prog)s run-now backup
  %(prog)s check
  %(prog)s daemon
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    # add
    add_parser = subparsers.add_parser("add", help="Ajouter une tâche planifiée")
    add_parser.add_argument("name", help="Nom de la tâche")
    add_parser.add_argument("cmd", help="Commande à exécuter")
    add_parser.add_argument("--interval", "-i", required=True, help="Intervalle (5m, 1h, 2d, 1w)")
    add_parser.add_argument("--disabled", action="store_true", help="Créer désactivée")

    # remove
    rm_parser = subparsers.add_parser("remove", help="Supprimer une tâche")
    rm_parser.add_argument("task_id", help="ID ou nom de la tâche")

    # enable/disable
    enable_parser = subparsers.add_parser("enable", help="Activer une tâche")
    enable_parser.add_argument("task_id", help="ID ou nom de la tâche")

    disable_parser = subparsers.add_parser("disable", help="Désactiver une tâche")
    disable_parser.add_argument("task_id", help="ID ou nom de la tâche")

    # list
    list_parser = subparsers.add_parser("list", help="Lister les tâches")
    list_parser.add_argument("--all", "-a", action="store_true", help="Inclure désactivées")

    # history
    hist_parser = subparsers.add_parser("history", help="Historique d'exécution")
    hist_parser.add_argument("--limit", "-n", type=int, default=10, help="Nombre d'entrées")

    # run-now
    run_parser = subparsers.add_parser("run-now", help="Exécuter immédiatement")
    run_parser.add_argument("task_id", help="ID ou nom de la tâche")

    # check
    subparsers.add_parser("check", help="Vérifier et exécuter les tâches dues")

    # daemon
    daemon_parser = subparsers.add_parser("daemon", help="Mode daemon continu")
    daemon_parser.add_argument("--interval", "-i", type=int, default=60, help="Intervalle de check (secondes)")

    args = parser.parse_args()

    if args.command == "add":
        add_task(args.name, args.cmd, args.interval, not args.disabled)

    elif args.command == "remove":
        remove_task(args.task_id)

    elif args.command == "enable":
        toggle_task(args.task_id, True)

    elif args.command == "disable":
        toggle_task(args.task_id, False)

    elif args.command == "list":
        list_tasks(args.all)

    elif args.command == "history":
        show_history(args.limit)

    elif args.command == "run-now":
        data = load_schedules()
        for task in data["tasks"]:
            if task["id"] == args.task_id or task["name"] == args.task_id:
                result = run_task(task)
                print(f"[{result['status']}] {task['name']} ({result['duration']:.1f}s)")
                if result.get("stderr"):
                    print(f"  stderr: {result['stderr'][:200]}")
                break
        else:
            print(f"[-] Tâche non trouvée: {args.task_id}")

    elif args.command == "check":
        executed = check_and_run()
        if not executed:
            print("[i] Aucune tâche à exécuter")
        else:
            for e in executed:
                print(f"[{e['status']}] {e['task_name']} ({e['duration']:.1f}s)")

    elif args.command == "daemon":
        daemon_mode(args.interval)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
