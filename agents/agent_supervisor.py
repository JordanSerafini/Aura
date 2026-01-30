#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Agent Supervisor v1.0
Coordination multi-agent avec state machine et agrégation des résultats.

Patterns implémentés:
- Supervisor pattern (Microsoft/LangGraph)
- State machine pour workflow
- Parallel execution
- Result aggregation
- Checkpoints
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
AGENTS_DIR = Path(__file__).parent
CHECKPOINTS_DIR = Path.home() / ".aura" / "checkpoints"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)


class TaskState(Enum):
    """États possibles d'une tâche."""
    PENDING = auto()
    ROUTING = auto()
    EXECUTING = auto()
    WAITING_RESULT = auto()
    AGGREGATING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class AgentResult:
    """Résultat d'exécution d'un agent."""
    agent: str
    success: bool
    output: str
    error: str = ""
    execution_time: float = 0.0
    return_code: int = 0


@dataclass
class SupervisedTask:
    """Tâche supervisée avec état."""
    id: str
    query: str
    state: TaskState = TaskState.PENDING
    primary_agent: str = ""
    secondary_agents: List[str] = field(default_factory=list)
    results: List[AgentResult] = field(default_factory=list)
    aggregated_result: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = ""
    checkpoints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentSupervisor:
    """Superviseur d'agents avec state machine."""

    def __init__(self, max_workers: int = 4, timeout: int = 120):
        self.max_workers = max_workers
        self.timeout = timeout
        self.active_tasks: Dict[str, SupervisedTask] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._task_counter = 0

        # Import du router
        try:
            from intent_router import IntentRouter
            self.router = IntentRouter(use_embeddings=True)
        except ImportError:
            self.router = None

        # Import du task runner
        try:
            from task_runner import TaskRunner
            self.task_runner = TaskRunner()
        except ImportError:
            self.task_runner = None

    def _generate_task_id(self) -> str:
        """Génère un ID unique."""
        self._task_counter += 1
        return f"sup_{datetime.now().strftime('%H%M%S')}_{self._task_counter}"

    def _update_state(self, task: SupervisedTask, new_state: TaskState):
        """Met à jour l'état d'une tâche."""
        old_state = task.state
        task.state = new_state
        task.updated_at = datetime.now().isoformat()
        task.checkpoints.append(f"{old_state.name} -> {new_state.name}")

    def _save_checkpoint(self, task: SupervisedTask) -> str:
        """Sauvegarde un checkpoint."""
        checkpoint_file = CHECKPOINTS_DIR / f"{task.id}_{task.state.name}.json"
        data = {
            "id": task.id,
            "query": task.query,
            "state": task.state.name,
            "primary_agent": task.primary_agent,
            "secondary_agents": task.secondary_agents,
            "results": [
                {
                    "agent": r.agent,
                    "success": r.success,
                    "output": r.output[:500],
                    "error": r.error,
                    "execution_time": r.execution_time
                }
                for r in task.results
            ],
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "checkpoints": task.checkpoints
        }
        checkpoint_file.write_text(json.dumps(data, indent=2))
        return str(checkpoint_file)

    def _execute_agent(self, agent: str, args: List[str] = None) -> AgentResult:
        """Exécute un agent et retourne le résultat."""
        agent_path = AGENTS_DIR / f"{agent}.py"
        if not agent_path.exists():
            return AgentResult(
                agent=agent,
                success=False,
                output="",
                error=f"Agent non trouvé: {agent}"
            )

        start_time = time.time()
        try:
            result = subprocess.run(
                [sys.executable, str(agent_path)] + (args or []),
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            execution_time = time.time() - start_time

            return AgentResult(
                agent=agent,
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
                execution_time=execution_time,
                return_code=result.returncode
            )

        except subprocess.TimeoutExpired:
            return AgentResult(
                agent=agent,
                success=False,
                output="",
                error=f"Timeout après {self.timeout}s",
                execution_time=self.timeout
            )
        except Exception as e:
            return AgentResult(
                agent=agent,
                success=False,
                output="",
                error=str(e),
                execution_time=time.time() - start_time
            )

    def _execute_parallel(self, agents: List[str], args_map: Dict[str, List[str]] = None) -> List[AgentResult]:
        """Exécute plusieurs agents en parallèle."""
        args_map = args_map or {}
        results = []

        futures = {
            self.executor.submit(self._execute_agent, agent, args_map.get(agent, [])): agent
            for agent in agents
        }

        for future in as_completed(futures, timeout=self.timeout * 2):
            agent = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append(AgentResult(
                    agent=agent,
                    success=False,
                    output="",
                    error=str(e)
                ))

        return results

    def _aggregate_results(self, task: SupervisedTask) -> str:
        """Agrège les résultats de plusieurs agents."""
        successful = [r for r in task.results if r.success]
        failed = [r for r in task.results if not r.success]

        aggregation = []

        # Résumé
        aggregation.append(f"=== Résultats agrégés ===")
        aggregation.append(f"Succès: {len(successful)}/{len(task.results)}")
        aggregation.append(f"Temps total: {sum(r.execution_time for r in task.results):.2f}s")
        aggregation.append("")

        # Résultats réussis
        for r in successful:
            aggregation.append(f"[{r.agent}] ({r.execution_time:.2f}s)")
            if r.output:
                # Garder les premières lignes significatives
                lines = [l for l in r.output.strip().split('\n') if l.strip()][:10]
                aggregation.append('\n'.join(lines))
            aggregation.append("")

        # Erreurs
        if failed:
            aggregation.append("=== Erreurs ===")
            for r in failed:
                aggregation.append(f"[{r.agent}] {r.error}")

        return '\n'.join(aggregation)

    def supervise(
        self,
        query: str,
        agents: List[str] = None,
        parallel: bool = False,
        background: bool = False
    ) -> SupervisedTask:
        """
        Supervise l'exécution d'une requête.

        Args:
            query: Requête utilisateur
            agents: Liste d'agents à exécuter (auto-route si None)
            parallel: Exécuter en parallèle
            background: Exécuter en arrière-plan

        Returns:
            SupervisedTask avec les résultats
        """
        task = SupervisedTask(
            id=self._generate_task_id(),
            query=query
        )
        self.active_tasks[task.id] = task

        # Phase 1: Routing
        self._update_state(task, TaskState.ROUTING)

        if agents:
            task.primary_agent = agents[0]
            task.secondary_agents = agents[1:]
        elif self.router:
            decision = self.router.route(query)
            task.primary_agent = decision.primary_agent
            task.secondary_agents = [a for a, _ in decision.secondary_agents]
            task.metadata["routing_confidence"] = decision.confidence
            task.metadata["run_background"] = decision.run_background

            # Override background si le router le suggère
            if decision.run_background:
                background = True
        else:
            return task  # Pas de routing possible

        if not task.primary_agent:
            self._update_state(task, TaskState.FAILED)
            task.metadata["error"] = "Aucun agent trouvé"
            return task

        self._save_checkpoint(task)

        # Phase 2: Execution
        self._update_state(task, TaskState.EXECUTING)

        all_agents = [task.primary_agent] + task.secondary_agents

        if background and self.task_runner:
            # Exécution en arrière-plan
            for agent in all_agents:
                bg_result = self.task_runner.run_agent(
                    agent=agent,
                    background=True,
                    notify=True
                )
                task.metadata[f"bg_task_{agent}"] = bg_result.get("task_id")

            self._update_state(task, TaskState.WAITING_RESULT)
            task.aggregated_result = f"Tâches lancées en background: {', '.join(all_agents)}"

        elif parallel:
            # Exécution parallèle
            task.results = self._execute_parallel(all_agents)
            self._update_state(task, TaskState.AGGREGATING)
            task.aggregated_result = self._aggregate_results(task)
            self._update_state(task, TaskState.COMPLETED)

        else:
            # Exécution séquentielle
            for agent in all_agents:
                result = self._execute_agent(agent)
                task.results.append(result)

                # Arrêter si l'agent principal échoue
                if agent == task.primary_agent and not result.success:
                    self._update_state(task, TaskState.FAILED)
                    task.aggregated_result = f"Échec de l'agent principal: {result.error}"
                    break

            if task.state != TaskState.FAILED:
                self._update_state(task, TaskState.AGGREGATING)
                task.aggregated_result = self._aggregate_results(task)
                self._update_state(task, TaskState.COMPLETED)

        self._save_checkpoint(task)
        return task

    def get_task(self, task_id: str) -> Optional[SupervisedTask]:
        """Récupère une tâche par son ID."""
        return self.active_tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Annule une tâche."""
        task = self.active_tasks.get(task_id)
        if task and task.state not in [TaskState.COMPLETED, TaskState.FAILED]:
            self._update_state(task, TaskState.CANCELLED)
            return True
        return False

    def list_tasks(self, state: TaskState = None) -> List[SupervisedTask]:
        """Liste les tâches."""
        tasks = list(self.active_tasks.values())
        if state:
            tasks = [t for t in tasks if t.state == state]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def resume_from_checkpoint(self, checkpoint_file: str) -> Optional[SupervisedTask]:
        """Reprend une tâche depuis un checkpoint."""
        try:
            data = json.loads(Path(checkpoint_file).read_text())
            task = SupervisedTask(
                id=data["id"],
                query=data["query"],
                state=TaskState[data["state"]],
                primary_agent=data["primary_agent"],
                secondary_agents=data["secondary_agents"],
                created_at=data["created_at"],
                checkpoints=data["checkpoints"]
            )
            self.active_tasks[task.id] = task

            # Reprendre selon l'état
            if task.state == TaskState.EXECUTING:
                return self.supervise(task.query, agents=[task.primary_agent] + task.secondary_agents)

            return task
        except Exception as e:
            print(f"Erreur lors de la reprise: {e}")
            return None

    def cleanup_checkpoints(self, days: int = 7) -> int:
        """Nettoie les vieux checkpoints."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        count = 0

        for f in CHECKPOINTS_DIR.glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff.timestamp():
                    f.unlink()
                    count += 1
            except Exception:
                pass

        return count


def supervise_query(query: str, parallel: bool = False, background: bool = False) -> Dict[str, Any]:
    """Fonction helper pour supervision rapide."""
    supervisor = AgentSupervisor()
    task = supervisor.supervise(query, parallel=parallel, background=background)

    return {
        "task_id": task.id,
        "state": task.state.name,
        "primary_agent": task.primary_agent,
        "secondary_agents": task.secondary_agents,
        "success": task.state == TaskState.COMPLETED,
        "result": task.aggregated_result,
        "execution_times": {r.agent: r.execution_time for r in task.results}
    }


def main():
    parser = argparse.ArgumentParser(
        description="Aura Agent Supervisor - Coordination multi-agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s run "Vérifie la santé du système et le réseau"
  %(prog)s run "Audit de sécurité" --background
  %(prog)s run "État complet" --parallel
  %(prog)s list
  %(prog)s status sup_123456
  %(prog)s resume /path/to/checkpoint.json
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    # run
    run_p = subparsers.add_parser("run", help="Exécuter une requête supervisée")
    run_p.add_argument("query", help="Requête à exécuter")
    run_p.add_argument("--agents", nargs="+", help="Agents spécifiques à utiliser")
    run_p.add_argument("--parallel", "-p", action="store_true", help="Exécution parallèle")
    run_p.add_argument("--background", "-b", action="store_true", help="Exécution en arrière-plan")
    run_p.add_argument("--json", action="store_true", help="Sortie JSON")

    # list
    list_p = subparsers.add_parser("list", help="Lister les tâches")
    list_p.add_argument("--state", choices=[s.name for s in TaskState])

    # status
    status_p = subparsers.add_parser("status", help="Statut d'une tâche")
    status_p.add_argument("task_id")

    # resume
    resume_p = subparsers.add_parser("resume", help="Reprendre depuis checkpoint")
    resume_p.add_argument("checkpoint_file")

    # cleanup
    clean_p = subparsers.add_parser("cleanup", help="Nettoyer les vieux checkpoints")
    clean_p.add_argument("--days", type=int, default=7)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    supervisor = AgentSupervisor()

    if args.command == "run":
        task = supervisor.supervise(
            query=args.query,
            agents=args.agents,
            parallel=args.parallel,
            background=args.background
        )

        if args.json:
            result = supervise_query(args.query, args.parallel, args.background)
            print(json.dumps(result, indent=2))
        else:
            print(f"Task ID: {task.id}")
            print(f"État: {task.state.name}")
            print(f"Agent principal: {task.primary_agent}")

            if task.secondary_agents:
                print(f"Agents secondaires: {', '.join(task.secondary_agents)}")

            print(f"\n{'='*50}")
            print(task.aggregated_result)

    elif args.command == "list":
        state = TaskState[args.state] if args.state else None
        tasks = supervisor.list_tasks(state=state)

        if not tasks:
            print("Aucune tâche.")
        else:
            print(f"{'ID':<20} {'État':<15} {'Agent':<20} {'Créé'}}")
            print("-" * 75)
            for t in tasks[:20]:
                print(f"{t.id:<20} {t.state.name:<15} {t.primary_agent:<20} {t.created_at[:19]}")

    elif args.command == "status":
        task = supervisor.get_task(args.task_id)
        if task:
            print(f"Task ID: {task.id}")
            print(f"Query: {task.query}")
            print(f"État: {task.state.name}")
            print(f"Agent principal: {task.primary_agent}")
            print(f"Checkpoints: {len(task.checkpoints)}")

            if task.results:
                print(f"\nRésultats:")
                for r in task.results:
                    status = "✓" if r.success else "✗"
                    print(f"  {status} {r.agent}: {r.execution_time:.2f}s")

            if task.aggregated_result:
                print(f"\nRésultat agrégé:")
                print(task.aggregated_result[:500])
        else:
            print(f"Tâche non trouvée: {args.task_id}")

    elif args.command == "resume":
        task = supervisor.resume_from_checkpoint(args.checkpoint_file)
        if task:
            print(f"Tâche reprise: {task.id}")
            print(f"État: {task.state.name}")
        else:
            print("Impossible de reprendre la tâche")

    elif args.command == "cleanup":
        count = supervisor.cleanup_checkpoints(days=args.days)
        print(f"Nettoyé: {count} checkpoint(s)")


if __name__ == "__main__":
    main()
