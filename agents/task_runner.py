#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Task Runner - Exécution d'agents en arrière-plan
Libère le terminal et notifie vocalement à la fin.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading

# Configuration
AGENTS_DIR = Path(__file__).parent
TASKS_DIR = Path.home() / ".aura" / "tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)

# PID file pour les tâches en cours
RUNNING_TASKS_FILE = TASKS_DIR / "running.json"


class TaskRunner:
    """Gestionnaire de tâches en arrière-plan."""

    def __init__(self):
        self.running_tasks = self._load_running_tasks()

    def _load_running_tasks(self) -> Dict[str, Any]:
        """Charge la liste des tâches en cours."""
        if RUNNING_TASKS_FILE.exists():
            try:
                return json.loads(RUNNING_TASKS_FILE.read_text())
            except Exception:
                return {}
        return {}

    def _save_running_tasks(self):
        """Sauvegarde la liste des tâches en cours."""
        RUNNING_TASKS_FILE.write_text(json.dumps(self.running_tasks, indent=2))

    def _generate_task_id(self) -> str:
        """Génère un ID unique pour une tâche."""
        return f"task_{datetime.now().strftime('%H%M%S')}_{os.getpid()}"

    def _notify_completion(self, task_id: str, success: bool, message: str):
        """Notifie vocalement la fin d'une tâche."""
        voice_script = AGENTS_DIR / "voice_speak.py"
        if voice_script.exists():
            status = "terminée avec succès" if success else "échouée"
            text = f"Tâche {status}. {message}"
            try:
                subprocess.run(
                    [sys.executable, str(voice_script), text],
                    capture_output=True,
                    timeout=30
                )
            except Exception:
                pass

    def run_agent(
        self,
        agent: str,
        args: List[str] = None,
        background: bool = True,
        notify: bool = True,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Exécute un agent Aura.

        Args:
            agent: Nom de l'agent (sans .py) ou chemin complet
            args: Arguments à passer à l'agent
            background: Exécuter en arrière-plan
            notify: Notifier vocalement à la fin
            timeout: Timeout en secondes (None = pas de timeout)

        Returns:
            Dict avec task_id, status, etc.
        """
        # Résoudre le chemin de l'agent
        if not agent.endswith('.py'):
            agent = f"{agent}.py"

        agent_path = AGENTS_DIR / agent
        if not agent_path.exists():
            # Essayer un chemin absolu
            agent_path = Path(agent)
            if not agent_path.exists():
                return {
                    "status": "error",
                    "message": f"Agent non trouvé: {agent}"
                }

        task_id = self._generate_task_id()
        cmd = [sys.executable, str(agent_path)] + (args or [])

        # Fichiers de sortie
        stdout_file = TASKS_DIR / f"{task_id}.stdout"
        stderr_file = TASKS_DIR / f"{task_id}.stderr"

        task_info = {
            "id": task_id,
            "agent": agent,
            "args": args or [],
            "started_at": datetime.now().isoformat(),
            "status": "running",
            "pid": None,
            "stdout_file": str(stdout_file),
            "stderr_file": str(stderr_file)
        }

        if background:
            # Exécution en arrière-plan
            with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
                process = subprocess.Popen(
                    cmd,
                    stdout=stdout_f,
                    stderr=stderr_f,
                    start_new_session=True  # Détache du terminal
                )

            task_info["pid"] = process.pid
            self.running_tasks[task_id] = task_info
            self._save_running_tasks()

            # Thread pour surveiller la fin et notifier
            if notify:
                def watch_and_notify():
                    process.wait()
                    success = process.returncode == 0
                    # Lire le résultat
                    try:
                        output = stdout_file.read_text()[-200:]  # Derniers 200 chars
                    except Exception:
                        output = ""

                    self._notify_completion(
                        task_id,
                        success,
                        f"{agent}: {output[:50]}..." if output else agent
                    )

                    # Mettre à jour le statut
                    task_info["status"] = "completed" if success else "failed"
                    task_info["completed_at"] = datetime.now().isoformat()
                    task_info["return_code"] = process.returncode
                    self.running_tasks[task_id] = task_info
                    self._save_running_tasks()

                thread = threading.Thread(target=watch_and_notify, daemon=True)
                thread.start()

            return {
                "status": "started",
                "task_id": task_id,
                "pid": process.pid,
                "message": f"Tâche lancée en arrière-plan. ID: {task_id}"
            }

        else:
            # Exécution synchrone
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )

                task_info["status"] = "completed" if result.returncode == 0 else "failed"
                task_info["return_code"] = result.returncode
                task_info["completed_at"] = datetime.now().isoformat()

                # Sauvegarder les sorties
                stdout_file.write_text(result.stdout)
                stderr_file.write_text(result.stderr)

                if notify:
                    self._notify_completion(
                        task_id,
                        result.returncode == 0,
                        agent
                    )

                return {
                    "status": "completed" if result.returncode == 0 else "failed",
                    "task_id": task_id,
                    "return_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }

            except subprocess.TimeoutExpired:
                return {
                    "status": "timeout",
                    "task_id": task_id,
                    "message": f"Timeout après {timeout}s"
                }

    def run_parallel(
        self,
        tasks: List[Dict[str, Any]],
        notify_each: bool = False,
        notify_all: bool = True
    ) -> Dict[str, Any]:
        """
        Exécute plusieurs agents en parallèle.

        Args:
            tasks: Liste de dicts {"agent": "...", "args": [...]}
            notify_each: Notifier pour chaque tâche
            notify_all: Notifier quand toutes sont terminées

        Returns:
            Dict avec les résultats
        """
        results = []
        processes = []

        for task in tasks:
            result = self.run_agent(
                agent=task.get("agent"),
                args=task.get("args", []),
                background=True,
                notify=notify_each
            )
            results.append(result)
            if result.get("pid"):
                processes.append((result["task_id"], result["pid"]))

        if notify_all and processes:
            def watch_all():
                # Attendre que tous les processus terminent
                for task_id, pid in processes:
                    try:
                        os.waitpid(pid, 0)
                    except Exception:
                        pass

                self._notify_completion(
                    "batch",
                    True,
                    f"{len(processes)} tâches terminées"
                )

            thread = threading.Thread(target=watch_all, daemon=True)
            thread.start()

        return {
            "status": "started",
            "tasks_count": len(results),
            "results": results
        }

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Liste les tâches."""
        tasks = list(self.running_tasks.values())

        if status:
            tasks = [t for t in tasks if t.get("status") == status]

        return sorted(tasks, key=lambda t: t.get("started_at", ""), reverse=True)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les infos d'une tâche."""
        task = self.running_tasks.get(task_id)
        if task:
            # Ajouter stdout/stderr si disponibles
            stdout_file = Path(task.get("stdout_file", ""))
            stderr_file = Path(task.get("stderr_file", ""))

            if stdout_file.exists():
                task["stdout"] = stdout_file.read_text()[-1000:]  # Derniers 1000 chars
            if stderr_file.exists():
                task["stderr"] = stderr_file.read_text()[-500:]

        return task

    def kill_task(self, task_id: str, force: bool = False) -> bool:
        """Tue une tâche en cours."""
        task = self.running_tasks.get(task_id)
        if not task or not task.get("pid"):
            return False

        try:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(task["pid"], sig)
            task["status"] = "killed"
            task["completed_at"] = datetime.now().isoformat()
            self._save_running_tasks()
            return True
        except ProcessLookupError:
            # Processus déjà terminé
            task["status"] = "completed"
            self._save_running_tasks()
            return True
        except Exception:
            return False

    def cleanup_old_tasks(self, days: int = 1) -> int:
        """Nettoie les vieilles tâches."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        to_delete = []

        for task_id, task in self.running_tasks.items():
            completed = task.get("completed_at")
            if completed:
                try:
                    if datetime.fromisoformat(completed) < cutoff:
                        to_delete.append(task_id)
                        # Supprimer les fichiers
                        for f in [task.get("stdout_file"), task.get("stderr_file")]:
                            if f and Path(f).exists():
                                Path(f).unlink()
                except Exception:
                    pass

        for task_id in to_delete:
            del self.running_tasks[task_id]

        self._save_running_tasks()
        return len(to_delete)


# Fonctions helper pour usage rapide
def run_bg(agent: str, *args, notify: bool = True) -> str:
    """Lance un agent en background. Retourne le task_id."""
    runner = TaskRunner()
    result = runner.run_agent(agent, list(args), background=True, notify=notify)
    return result.get("task_id", "")


def run_parallel_bg(tasks: List[tuple]) -> Dict[str, Any]:
    """Lance plusieurs agents en parallèle.

    Args:
        tasks: Liste de tuples (agent, [args])

    Returns:
        Dict avec les résultats
    """
    runner = TaskRunner()
    task_list = [{"agent": t[0], "args": list(t[1]) if len(t) > 1 else []} for t in tasks]
    return runner.run_parallel(task_list)


# CLI
def main():
    parser = argparse.ArgumentParser(
        description="Aura Task Runner - Exécution d'agents en arrière-plan",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s run sys_health --background
  %(prog)s run security_auditor audit --notify
  %(prog)s parallel "sys_health" "network_monitor status"
  %(prog)s list --status running
  %(prog)s status task_123456
  %(prog)s kill task_123456
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    # run
    run_p = subparsers.add_parser("run", help="Exécuter un agent")
    run_p.add_argument("agent", help="Nom de l'agent")
    run_p.add_argument("args", nargs="*", help="Arguments")
    run_p.add_argument("--foreground", "-f", action="store_true", help="Exécuter en foreground")
    run_p.add_argument("--no-notify", action="store_true", help="Pas de notification vocale")
    run_p.add_argument("--timeout", type=int, help="Timeout en secondes")

    # parallel
    par_p = subparsers.add_parser("parallel", help="Exécuter plusieurs agents en parallèle")
    par_p.add_argument("tasks", nargs="+", help="Agents à exécuter (format: 'agent arg1 arg2')")

    # list
    list_p = subparsers.add_parser("list", help="Lister les tâches")
    list_p.add_argument("--status", choices=["running", "completed", "failed", "killed"])

    # status
    status_p = subparsers.add_parser("status", help="Statut d'une tâche")
    status_p.add_argument("task_id")

    # kill
    kill_p = subparsers.add_parser("kill", help="Tuer une tâche")
    kill_p.add_argument("task_id")
    kill_p.add_argument("--force", "-f", action="store_true")

    # cleanup
    clean_p = subparsers.add_parser("cleanup", help="Nettoyer les vieilles tâches")
    clean_p.add_argument("--days", type=int, default=1)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    runner = TaskRunner()

    if args.command == "run":
        result = runner.run_agent(
            agent=args.agent,
            args=args.args,
            background=not args.foreground,
            notify=not args.no_notify,
            timeout=args.timeout
        )
        print(json.dumps(result, indent=2))

        if result.get("status") == "started":
            print(f"\n✓ Tâche lancée en arrière-plan")
            print(f"  ID: {result.get('task_id')}")
            print(f"  PID: {result.get('pid')}")
            print(f"\nTerminal libéré. Tu seras notifié vocalement à la fin.")

    elif args.command == "parallel":
        tasks = []
        for task_str in args.tasks:
            parts = task_str.split()
            tasks.append({"agent": parts[0], "args": parts[1:] if len(parts) > 1 else []})

        result = runner.run_parallel(tasks)
        print(json.dumps(result, indent=2))
        print(f"\n✓ {len(tasks)} tâches lancées en parallèle")

    elif args.command == "list":
        tasks = runner.list_tasks(status=args.status)
        if not tasks:
            print("Aucune tâche.")
        else:
            print(f"{'ID':<20} {'Agent':<20} {'Status':<12} {'Started'}")
            print("-" * 70)
            for t in tasks[:20]:
                print(f"{t.get('id', 'N/A'):<20} {t.get('agent', 'N/A'):<20} {t.get('status', 'N/A'):<12} {t.get('started_at', 'N/A')[:19]}")

    elif args.command == "status":
        task = runner.get_task(args.task_id)
        if task:
            print(json.dumps(task, indent=2))
        else:
            print(f"Tâche non trouvée: {args.task_id}")

    elif args.command == "kill":
        if runner.kill_task(args.task_id, force=args.force):
            print(f"Tâche {args.task_id} terminée.")
        else:
            print(f"Impossible de terminer la tâche {args.task_id}")

    elif args.command == "cleanup":
        count = runner.cleanup_old_tasks(days=args.days)
        print(f"Nettoyé: {count} tâche(s)")


if __name__ == "__main__":
    main()
