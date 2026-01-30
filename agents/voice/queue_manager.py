"""
AURA-OS Voice Queue Manager
Gestion de la file d'attente des messages vocaux
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Awaitable
from datetime import datetime
import uuid


class Priority(Enum):
    """Priorités des messages vocaux"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass(order=True)
class QueueItem:
    """Item dans la queue de messages vocaux"""
    priority: int
    timestamp: float = field(compare=False)
    id: str = field(compare=False)
    text: str = field(compare=False)
    voice: str | None = field(compare=False, default=None)
    callback: Callable | None = field(compare=False, default=None)

    def __post_init__(self):
        # Inverser la priorité pour que HIGH passe avant LOW dans le heap
        self.priority = -self.priority


class VoiceQueueManager:
    """Gestionnaire de file d'attente pour les messages vocaux"""

    def __init__(self, max_queue_size: int = 50):
        self.max_queue_size = max_queue_size
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self._current_item: QueueItem | None = None
        self._is_playing = False
        self._is_running = False
        self._speak_callback: Callable[[str, Optional[str | None], Awaitable[bool]]] = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        # Stats
        self._total_processed = 0
        self._total_dropped = 0

    def set_speak_callback(self, callback: Callable[[str, str | None], Awaitable[bool]]):
        """Définit la fonction de synthèse vocale à appeler"""
        self._speak_callback = callback

    async def start(self):
        """Démarre le processeur de queue"""
        if self._is_running:
            return

        self._is_running = True
        self._task = asyncio.create_task(self._process_queue())

    async def stop(self):
        """Arrête le processeur de queue"""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def enqueue(
        self,
        text: str,
        voice: str | None = None,
        priority: Priority = Priority.NORMAL,
        callback: Callable | None = None
    ) -> str | None:
        """Ajoute un message à la queue"""

        # Si urgent, interrompre le message en cours
        if priority == Priority.URGENT:
            await self._interrupt_current()

        item = QueueItem(
            priority=priority.value,
            timestamp=datetime.now().timestamp(),
            id=str(uuid.uuid4())[:8],
            text=text,
            voice=voice,
            callback=callback
        )

        try:
            self._queue.put_nowait(item)
            return item.id
        except asyncio.QueueFull:
            # Queue pleine, supprimer le message le moins prioritaire
            self._total_dropped += 1
            return None

    async def _process_queue(self):
        """Traite la queue en continu"""
        while self._is_running:
            try:
                # Attendre le prochain item
                item = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )

                async with self._lock:
                    self._current_item = item
                    self._is_playing = True

                # Synthétiser et jouer
                if self._speak_callback:
                    try:
                        success = await self._speak_callback(item.text, item.voice)

                        if item.callback:
                            try:
                                await item.callback(success)
                            except Exception:
                                pass

                        self._total_processed += 1

                    except Exception as e:
                        print(f"Queue error: {e}")

                async with self._lock:
                    self._current_item = None
                    self._is_playing = False

                self._queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Queue processor error: {e}")
                await asyncio.sleep(0.1)

    async def _interrupt_current(self):
        """Interrompt le message en cours (pour les urgents)"""
        # Note: L'interruption réelle dépend du player audio
        # Pour l'instant, on marque juste qu'on veut interrompre
        async with self._lock:
            if self._is_playing:
                # TODO: Implémenter l'interruption du player audio
                pass

    async def clear(self):
        """Vide la queue"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    def get_queue_size(self) -> int:
        """Retourne la taille actuelle de la queue"""
        return self._queue.qsize()

    def is_playing(self) -> bool:
        """Vérifie si un message est en cours de lecture"""
        return self._is_playing

    def get_stats(self) -> dict:
        """Retourne les statistiques de la queue"""
        return {
            "queue_size": self._queue.qsize(),
            "max_size": self.max_queue_size,
            "is_playing": self._is_playing,
            "total_processed": self._total_processed,
            "total_dropped": self._total_dropped,
            "current_text": self._current_item.text[:30] if self._current_item else None
        }


# Singleton pour accès global
_queue_manager: VoiceQueueManager | None = None


def get_queue_manager() -> VoiceQueueManager:
    """Retourne l'instance singleton du queue manager"""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = VoiceQueueManager()
    return _queue_manager
