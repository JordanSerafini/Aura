#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Error Handler v1.0
Gestion des erreurs avec retry, fallback et circuit breaker.

Patterns implémentés:
- Retry avec exponential backoff
- Circuit breaker (fail fast après N erreurs)
- Fallback agents
- Error logging et notification
"""

import argparse
import functools
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar
import threading

# Configuration
AGENTS_DIR = Path(__file__).parent
ERROR_LOG_DIR = Path.home() / ".aura" / "error_logs"
ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
CIRCUIT_STATE_FILE = Path.home() / ".aura" / "circuit_states.json"

# Types
T = TypeVar('T')


class CircuitState(Enum):
    """États du circuit breaker."""
    CLOSED = auto()     # Normal, tout passe
    OPEN = auto()       # Ouvert, fail fast
    HALF_OPEN = auto()  # Test pour voir si ça remarche


@dataclass
class RetryConfig:
    """Configuration de retry."""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class CircuitBreakerConfig:
    """Configuration du circuit breaker."""
    failure_threshold: int = 5      # Nombre d'échecs avant ouverture
    success_threshold: int = 2      # Succès en half-open avant fermeture
    timeout: int = 60               # Secondes avant de passer en half-open
    half_open_max_calls: int = 3    # Appels max en half-open


@dataclass
class ErrorRecord:
    """Enregistrement d'une erreur."""
    agent: str
    error_type: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    context: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution: str = ""


@dataclass
class CircuitBreakerState:
    """État d'un circuit breaker."""
    agent: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[str] = None
    half_open_calls: int = 0


# Fallback mappings
FALLBACK_AGENTS: Dict[str, List[str]] = {
    "voice_speak": ["voice_speak_piper"],
    "network_monitor": ["security_auditor"],
    "sys_health": ["process_manager"],
    "tech_watcher": [],  # Pas de fallback
    "memory_manager": [],
    "screenshot_ocr": [],
}


class RetryError(Exception):
    """Erreur après épuisement des retries."""
    pass


class CircuitOpenError(Exception):
    """Erreur quand le circuit est ouvert."""
    pass


class ErrorHandler:
    """Gestionnaire d'erreurs centralisé."""

    def __init__(self):
        self.circuit_states: Dict[str, CircuitBreakerState] = {}
        self.error_history: List[ErrorRecord] = []
        self._lock = threading.Lock()
        self._load_circuit_states()

    def _load_circuit_states(self):
        """Charge les états des circuits."""
        if CIRCUIT_STATE_FILE.exists():
            try:
                data = json.loads(CIRCUIT_STATE_FILE.read_text())
                for agent, state_data in data.items():
                    self.circuit_states[agent] = CircuitBreakerState(
                        agent=agent,
                        state=CircuitState[state_data.get("state", "CLOSED")],
                        failure_count=state_data.get("failure_count", 0),
                        success_count=state_data.get("success_count", 0),
                        last_failure_time=state_data.get("last_failure_time")
                    )
            except Exception:
                pass

    def _save_circuit_states(self):
        """Sauvegarde les états des circuits."""
        data = {}
        for agent, state in self.circuit_states.items():
            data[agent] = {
                "state": state.state.name,
                "failure_count": state.failure_count,
                "success_count": state.success_count,
                "last_failure_time": state.last_failure_time
            }
        CIRCUIT_STATE_FILE.write_text(json.dumps(data, indent=2))

    def _get_circuit_state(self, agent: str) -> CircuitBreakerState:
        """Récupère ou crée l'état du circuit pour un agent."""
        if agent not in self.circuit_states:
            self.circuit_states[agent] = CircuitBreakerState(agent=agent)
        return self.circuit_states[agent]

    def _check_circuit(self, agent: str, config: CircuitBreakerConfig) -> bool:
        """
        Vérifie si l'appel est autorisé selon le circuit breaker.
        Retourne True si l'appel est autorisé.
        """
        with self._lock:
            state = self._get_circuit_state(agent)

            if state.state == CircuitState.CLOSED:
                return True

            elif state.state == CircuitState.OPEN:
                # Vérifier si le timeout est passé
                if state.last_failure_time:
                    last_failure = datetime.fromisoformat(state.last_failure_time)
                    if datetime.now() - last_failure > timedelta(seconds=config.timeout):
                        state.state = CircuitState.HALF_OPEN
                        state.half_open_calls = 0
                        self._save_circuit_states()
                        return True
                return False

            else:  # HALF_OPEN
                if state.half_open_calls < config.half_open_max_calls:
                    state.half_open_calls += 1
                    return True
                return False

    def _record_success(self, agent: str, config: CircuitBreakerConfig):
        """Enregistre un succès."""
        with self._lock:
            state = self._get_circuit_state(agent)

            if state.state == CircuitState.HALF_OPEN:
                state.success_count += 1
                if state.success_count >= config.success_threshold:
                    state.state = CircuitState.CLOSED
                    state.failure_count = 0
                    state.success_count = 0
            else:
                state.failure_count = max(0, state.failure_count - 1)

            self._save_circuit_states()

    def _record_failure(self, agent: str, error: str, config: CircuitBreakerConfig):
        """Enregistre un échec."""
        with self._lock:
            state = self._get_circuit_state(agent)
            state.failure_count += 1
            state.last_failure_time = datetime.now().isoformat()

            if state.state == CircuitState.HALF_OPEN:
                state.state = CircuitState.OPEN
                state.success_count = 0
            elif state.failure_count >= config.failure_threshold:
                state.state = CircuitState.OPEN

            self._save_circuit_states()

            # Logger l'erreur
            self._log_error(ErrorRecord(
                agent=agent,
                error_type="execution_failure",
                message=error,
                context={"circuit_state": state.state.name}
            ))

    def _log_error(self, error: ErrorRecord):
        """Log une erreur."""
        self.error_history.append(error)

        # Écrire dans le fichier de log
        log_file = ERROR_LOG_DIR / f"errors_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps({
                "agent": error.agent,
                "error_type": error.error_type,
                "message": error.message,
                "timestamp": error.timestamp,
                "context": error.context
            }) + "\n")

    def _calculate_delay(self, attempt: int, config: RetryConfig) -> float:
        """Calcule le délai avant le prochain retry."""
        delay = min(
            config.initial_delay * (config.exponential_base ** attempt),
            config.max_delay
        )

        if config.jitter:
            import random
            delay *= (0.5 + random.random())

        return delay

    def retry_with_backoff(
        self,
        func: Callable[..., T],
        config: RetryConfig = None,
        on_retry: Callable[[int, Exception], None] = None
    ) -> T:
        """
        Exécute une fonction avec retry et exponential backoff.

        Args:
            func: Fonction à exécuter
            config: Configuration de retry
            on_retry: Callback appelé à chaque retry

        Returns:
            Résultat de la fonction

        Raises:
            RetryError: Après épuisement des retries
        """
        config = config or RetryConfig()
        last_exception = None

        for attempt in range(config.max_attempts):
            try:
                return func()
            except Exception as e:
                last_exception = e

                if attempt < config.max_attempts - 1:
                    delay = self._calculate_delay(attempt, config)

                    if on_retry:
                        on_retry(attempt + 1, e)

                    time.sleep(delay)

        raise RetryError(
            f"Échec après {config.max_attempts} tentatives: {last_exception}"
        )

    def execute_with_circuit_breaker(
        self,
        agent: str,
        args: List[str] = None,
        config: CircuitBreakerConfig = None,
        retry_config: RetryConfig = None
    ) -> Dict[str, Any]:
        """
        Exécute un agent avec circuit breaker et retry.

        Args:
            agent: Nom de l'agent
            args: Arguments
            config: Config du circuit breaker
            retry_config: Config de retry

        Returns:
            Dict avec résultat ou erreur
        """
        config = config or CircuitBreakerConfig()
        retry_config = retry_config or RetryConfig()

        # Vérifier le circuit
        if not self._check_circuit(agent, config):
            # Essayer le fallback
            fallbacks = FALLBACK_AGENTS.get(agent, [])
            for fallback in fallbacks:
                if self._check_circuit(fallback, config):
                    return self.execute_with_circuit_breaker(
                        fallback, args, config, retry_config
                    )

            raise CircuitOpenError(f"Circuit ouvert pour {agent}, pas de fallback disponible")

        agent_path = AGENTS_DIR / f"{agent}.py"
        if not agent_path.exists():
            return {"success": False, "error": f"Agent non trouvé: {agent}"}

        def execute():
            result = subprocess.run(
                [sys.executable, str(agent_path)] + (args or []),
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode != 0:
                raise Exception(result.stderr or f"Return code: {result.returncode}")
            return result

        try:
            result = self.retry_with_backoff(
                execute,
                config=retry_config,
                on_retry=lambda a, e: print(f"Retry {a} pour {agent}: {e}")
            )

            self._record_success(agent, config)

            return {
                "success": True,
                "agent": agent,
                "output": result.stdout,
                "return_code": result.returncode
            }

        except (RetryError, subprocess.TimeoutExpired) as e:
            self._record_failure(agent, str(e), config)

            # Essayer fallback
            fallbacks = FALLBACK_AGENTS.get(agent, [])
            for fallback in fallbacks:
                try:
                    return self.execute_with_circuit_breaker(
                        fallback, args, config, retry_config
                    )
                except Exception:
                    continue

            return {
                "success": False,
                "agent": agent,
                "error": str(e),
                "fallbacks_tried": fallbacks
            }

    def execute_with_fallback(
        self,
        agent: str,
        args: List[str] = None,
        fallbacks: List[str] = None
    ) -> Dict[str, Any]:
        """
        Exécute un agent avec fallback automatique.

        Args:
            agent: Agent principal
            args: Arguments
            fallbacks: Liste de fallbacks (ou auto)

        Returns:
            Résultat de l'exécution
        """
        fallbacks = fallbacks or FALLBACK_AGENTS.get(agent, [])
        agents_to_try = [agent] + fallbacks

        for current_agent in agents_to_try:
            agent_path = AGENTS_DIR / f"{current_agent}.py"
            if not agent_path.exists():
                continue

            try:
                result = subprocess.run(
                    [sys.executable, str(agent_path)] + (args or []),
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    return {
                        "success": True,
                        "agent": current_agent,
                        "output": result.stdout,
                        "was_fallback": current_agent != agent
                    }

            except Exception as e:
                self._log_error(ErrorRecord(
                    agent=current_agent,
                    error_type="execution_error",
                    message=str(e)
                ))
                continue

        return {
            "success": False,
            "agent": agent,
            "error": "Tous les agents ont échoué",
            "tried": agents_to_try
        }

    def get_circuit_status(self) -> Dict[str, Any]:
        """Retourne le statut de tous les circuits."""
        return {
            agent: {
                "state": state.state.name,
                "failure_count": state.failure_count,
                "last_failure": state.last_failure_time
            }
            for agent, state in self.circuit_states.items()
        }

    def reset_circuit(self, agent: str) -> bool:
        """Reset un circuit breaker."""
        if agent in self.circuit_states:
            self.circuit_states[agent] = CircuitBreakerState(agent=agent)
            self._save_circuit_states()
            return True
        return False

    def get_recent_errors(self, hours: int = 24, agent: str = None) -> List[ErrorRecord]:
        """Récupère les erreurs récentes."""
        cutoff = datetime.now() - timedelta(hours=hours)
        errors = []

        # Lire les fichiers de log
        for log_file in ERROR_LOG_DIR.glob("errors_*.jsonl"):
            try:
                for line in log_file.read_text().strip().split('\n'):
                    if not line:
                        continue
                    data = json.loads(line)
                    if datetime.fromisoformat(data["timestamp"]) > cutoff:
                        if agent is None or data["agent"] == agent:
                            errors.append(ErrorRecord(**data))
            except Exception:
                continue

        return sorted(errors, key=lambda e: e.timestamp, reverse=True)


# Décorateur pour retry
def with_retry(config: RetryConfig = None):
    """Décorateur pour ajouter du retry à une fonction."""
    config = config or RetryConfig()
    handler = ErrorHandler()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return handler.retry_with_backoff(
                lambda: func(*args, **kwargs),
                config=config
            )
        return wrapper
    return decorator


def main():
    parser = argparse.ArgumentParser(
        description="Aura Error Handler - Gestion des erreurs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s execute sys_health --retry 3
  %(prog)s status
  %(prog)s errors --hours 24
  %(prog)s reset sys_health
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    # execute
    exec_p = subparsers.add_parser("execute", help="Exécuter un agent avec protection")
    exec_p.add_argument("agent", help="Agent à exécuter")
    exec_p.add_argument("args", nargs="*", help="Arguments")
    exec_p.add_argument("--retry", type=int, default=3, help="Nombre de retries")
    exec_p.add_argument("--no-circuit", action="store_true", help="Désactiver circuit breaker")

    # status
    subparsers.add_parser("status", help="Statut des circuit breakers")

    # errors
    err_p = subparsers.add_parser("errors", help="Voir les erreurs récentes")
    err_p.add_argument("--hours", type=int, default=24)
    err_p.add_argument("--agent")

    # reset
    reset_p = subparsers.add_parser("reset", help="Reset un circuit breaker")
    reset_p.add_argument("agent")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler = ErrorHandler()

    if args.command == "execute":
        retry_config = RetryConfig(max_attempts=args.retry)

        if args.no_circuit:
            result = handler.execute_with_fallback(args.agent, args.args)
        else:
            try:
                result = handler.execute_with_circuit_breaker(
                    args.agent, args.args, retry_config=retry_config
                )
            except CircuitOpenError as e:
                result = {"success": False, "error": str(e)}

        print(json.dumps(result, indent=2))

    elif args.command == "status":
        status = handler.get_circuit_status()
        if not status:
            print("Aucun circuit breaker actif.")
        else:
            print(f"{'Agent':<25} {'État':<12} {'Échecs':<10} Dernier échec")
            print("-" * 70)
            for agent, data in status.items():
                last = data["last_failure"][:19] if data["last_failure"] else "N/A"
                print(f"{agent:<25} {data['state']:<12} {data['failure_count']:<10} {last}")

    elif args.command == "errors":
        errors = handler.get_recent_errors(hours=args.hours, agent=args.agent)
        if not errors:
            print("Aucune erreur récente.")
        else:
            print(f"Erreurs des dernières {args.hours}h:\n")
            for e in errors[:20]:
                print(f"[{e.timestamp[:19]}] {e.agent}: {e.message[:60]}")

    elif args.command == "reset":
        if handler.reset_circuit(args.agent):
            print(f"Circuit breaker reset pour: {args.agent}")
        else:
            print(f"Aucun circuit breaker pour: {args.agent}")


if __name__ == "__main__":
    main()
