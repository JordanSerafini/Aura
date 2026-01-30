#!/home/tinkerbell/.aura/venv/bin/python3
"""
AURA Memory Scheduler v1.0 - Consolidation mémoire automatique
Exécute des tâches de maintenance mémoire de façon planifiée.

Team: core (memory)

Features:
- Consolidation épisodes → skills (quotidienne)
- Nettoyage des vieux épisodes (hebdomadaire)
- Indexation RAG incrémentale
- Garbage collection

Usage:
  python3 memory_scheduler.py run      # Lance les tâches dues
  python3 memory_scheduler.py status   # État des tâches
  python3 memory_scheduler.py force TASK  # Force une tâche
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


SCHEDULER_DIR = Path.home() / ".aura" / "scheduler"
SCHEDULER_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = SCHEDULER_DIR / "memory_state.json"
LOG_FILE = SCHEDULER_DIR / "memory_scheduler.log"


class ScheduledTask:
    """Définition d'une tâche planifiée."""

    def __init__(
        self,
        name: str,
        command: list[str],
        interval_hours: float,
        description: str = "",
        on_failure: str = "continue"
    ):
        self.name = name
        self.command = command
        self.interval_hours = interval_hours
        self.description = description
        self.on_failure = on_failure  # continue, retry, stop


# Tâches de maintenance mémoire
SCHEDULED_TASKS = [
    ScheduledTask(
        name="consolidate_memory",
        command=[
            sys.executable,
            str(Path.home() / ".aura/agents/memory/memory_api.py"),
            "consolidate"
        ],
        interval_hours=24,
        description="Consolide les épisodes en skills"
    ),
    ScheduledTask(
        name="cleanup_old_episodes",
        command=[
            sys.executable,
            str(Path.home() / ".aura/agents/memory_manager.py"),
            "cleanup", "--days", "30"
        ],
        interval_hours=168,  # 7 jours
        description="Nettoie les vieux épisodes"
    ),
    ScheduledTask(
        name="reindex_rag",
        command=[
            sys.executable,
            str(Path.home() / ".aura/agents/memory_manager.py"),
            "index", str(Path.home() / ".aura")
        ],
        interval_hours=72,  # 3 jours
        description="Réindexe les documents RAG"
    ),
    ScheduledTask(
        name="analyze_patterns",
        command=[
            sys.executable,
            str(Path.home() / ".aura/agents/self_reflection.py"),
            "meta", "--count", "50"
        ],
        interval_hours=12,
        description="Analyse les patterns de réflexion"
    ),
]


class MemoryScheduler:
    """Gestionnaire de tâches planifiées pour la mémoire."""

    def __init__(self):
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """Charge l'état des exécutions."""
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except Exception:
                pass
        return {"last_run": {}, "run_count": {}, "failures": {}}

    def _save_state(self) -> None:
        """Sauvegarde l'état."""
        STATE_FILE.write_text(json.dumps(self.state, indent=2))

    def _log(self, message: str) -> None:
        """Log un message."""
        timestamp = datetime.now().isoformat()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
        print(f"[{timestamp}] {message}")

    def is_due(self, task: ScheduledTask) -> bool:
        """Vérifie si une tâche doit être exécutée."""
        last_run_str = self.state["last_run"].get(task.name)
        if not last_run_str:
            return True

        last_run = datetime.fromisoformat(last_run_str)
        next_run = last_run + timedelta(hours=task.interval_hours)
        return datetime.now() >= next_run

    def time_until_next(self, task: ScheduledTask) -> timedelta | None:
        """Calcule le temps jusqu'à la prochaine exécution."""
        last_run_str = self.state["last_run"].get(task.name)
        if not last_run_str:
            return timedelta(0)

        last_run = datetime.fromisoformat(last_run_str)
        next_run = last_run + timedelta(hours=task.interval_hours)
        delta = next_run - datetime.now()
        return delta if delta.total_seconds() > 0 else timedelta(0)

    def run_task(self, task: ScheduledTask, force: bool = False) -> bool:
        """
        Exécute une tâche.

        Args:
            task: La tâche à exécuter
            force: Forcer l'exécution même si pas due

        Returns:
            True si succès
        """
        if not force and not self.is_due(task):
            return True

        self._log(f"Starting task: {task.name}")

        try:
            result = subprocess.run(
                task.command,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes max
            )

            if result.returncode == 0:
                self._log(f"Task {task.name} completed successfully")
                self.state["last_run"][task.name] = datetime.now().isoformat()
                self.state["run_count"][task.name] = self.state["run_count"].get(task.name, 0) + 1
                self.state["failures"].pop(task.name, None)
                self._save_state()
                return True
            else:
                self._log(f"Task {task.name} failed: {result.stderr}")
                self.state["failures"][task.name] = {
                    "time": datetime.now().isoformat(),
                    "error": result.stderr[:500]
                }
                self._save_state()
                return False

        except subprocess.TimeoutExpired:
            self._log(f"Task {task.name} timed out")
            self.state["failures"][task.name] = {
                "time": datetime.now().isoformat(),
                "error": "Timeout after 300s"
            }
            self._save_state()
            return False

        except Exception as e:
            self._log(f"Task {task.name} error: {e}")
            self.state["failures"][task.name] = {
                "time": datetime.now().isoformat(),
                "error": str(e)
            }
            self._save_state()
            return False

    def run_all_due(self) -> dict:
        """Exécute toutes les tâches dues."""
        results = {}
        for task in SCHEDULED_TASKS:
            if self.is_due(task):
                results[task.name] = self.run_task(task)
            else:
                results[task.name] = None  # Not due
        return results

    def get_status(self) -> dict:
        """Retourne l'état de toutes les tâches."""
        status = {}
        for task in SCHEDULED_TASKS:
            time_until = self.time_until_next(task)
            status[task.name] = {
                "description": task.description,
                "interval_hours": task.interval_hours,
                "last_run": self.state["last_run"].get(task.name),
                "run_count": self.state["run_count"].get(task.name, 0),
                "is_due": self.is_due(task),
                "time_until_next": str(time_until) if time_until else "Now",
                "last_failure": self.state["failures"].get(task.name)
            }
        return status

    def force_task(self, task_name: str) -> bool:
        """Force l'exécution d'une tâche."""
        for task in SCHEDULED_TASKS:
            if task.name == task_name:
                return self.run_task(task, force=True)
        return False


def print_status(status: dict) -> None:
    """Affiche le statut joliment."""
    print("\n" + "=" * 60)
    print("  AURA Memory Scheduler Status")
    print("=" * 60 + "\n")

    for name, info in status.items():
        due_marker = "🔴 DUE" if info["is_due"] else "🟢 OK"
        print(f"  [{due_marker}] {name}")
        print(f"       {info['description']}")
        print(f"       Interval: {info['interval_hours']}h | Runs: {info['run_count']}")
        print(f"       Last: {info['last_run'] or 'Never'}")
        print(f"       Next in: {info['time_until_next']}")
        if info["last_failure"]:
            print(f"       ⚠️ Last failure: {info['last_failure']['error'][:50]}")
        print()

    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="AURA Memory Scheduler")
    subparsers = parser.add_subparsers(dest="command")

    # run
    subparsers.add_parser("run", help="Exécute les tâches dues")

    # status
    subparsers.add_parser("status", help="Affiche l'état")

    # force
    force_p = subparsers.add_parser("force", help="Force une tâche")
    force_p.add_argument("task", help="Nom de la tâche")

    # list
    subparsers.add_parser("list", help="Liste les tâches")

    args = parser.parse_args()

    scheduler = MemoryScheduler()

    if args.command == "run":
        results = scheduler.run_all_due()
        print("\nExecution results:")
        for task, success in results.items():
            if success is None:
                print(f"  ⏭️  {task}: Not due")
            elif success:
                print(f"  ✅ {task}: Success")
            else:
                print(f"  ❌ {task}: Failed")

    elif args.command == "status":
        status = scheduler.get_status()
        print_status(status)

    elif args.command == "force":
        success = scheduler.force_task(args.task)
        if success:
            print(f"✅ Task '{args.task}' completed")
        else:
            print(f"❌ Task '{args.task}' failed or not found")

    elif args.command == "list":
        print("\nAvailable tasks:")
        for task in SCHEDULED_TASKS:
            print(f"  - {task.name}: {task.description} (every {task.interval_hours}h)")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
