"""
AURA-OS Voice Cache
Cache intelligent pour les synthèses vocales fréquentes
"""

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import aiofiles
import aiofiles.os


@dataclass
class CacheEntry:
    """Entrée de cache"""
    text_hash: str
    voice: str
    engine: str
    file_path: str
    created_at: float
    last_accessed: float
    access_count: int
    size_bytes: int


class VoiceCache:
    """Cache intelligent pour les synthèses vocales"""

    def __init__(self, cache_dir: Optional[Path] = None, max_size_mb: int = 100):
        self.cache_dir = cache_dir or Path.home() / ".aura" / "voice" / "cache"
        self.index_file = self.cache_dir / "index.json"
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.entries: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

        # Phrases pré-cachées (fréquentes)
        self.preload_phrases = [
            "Tâche terminée.",
            "J'analyse la situation.",
            "C'est fait.",
            "Je lance l'opération.",
            "Une erreur s'est produite.",
            "Je vérifie.",
            "Opération réussie.",
            "Compris.",
            "Je m'en occupe.",
            "Attends une seconde.",
        ]

    async def initialize(self):
        """Initialise le cache"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        await self._load_index()

    async def _load_index(self):
        """Charge l'index du cache"""
        if self.index_file.exists():
            try:
                async with aiofiles.open(self.index_file, 'r') as f:
                    data = json.loads(await f.read())
                    self.entries = {
                        k: CacheEntry(**v) for k, v in data.items()
                    }
            except Exception:
                self.entries = {}

    async def _save_index(self):
        """Sauvegarde l'index du cache"""
        try:
            async with aiofiles.open(self.index_file, 'w') as f:
                data = {k: asdict(v) for k, v in self.entries.items()}
                await f.write(json.dumps(data, indent=2))
        except Exception:
            pass

    def _get_cache_key(self, text: str, voice: str, engine: str) -> str:
        """Génère une clé de cache unique"""
        content = f"{text}|{voice}|{engine}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def get(self, text: str, voice: str, engine: str) -> Optional[bytes]:
        """Récupère un audio depuis le cache"""
        cache_key = self._get_cache_key(text, voice, engine)

        async with self._lock:
            entry = self.entries.get(cache_key)
            if not entry:
                return None

            # Vérifier que le fichier existe
            if not Path(entry.file_path).exists():
                del self.entries[cache_key]
                await self._save_index()
                return None

            # Mettre à jour les stats
            entry.last_accessed = time.time()
            entry.access_count += 1
            await self._save_index()

            # Lire le fichier
            async with aiofiles.open(entry.file_path, 'rb') as f:
                return await f.read()

    async def put(self, text: str, voice: str, engine: str, audio_data: bytes) -> str:
        """Stocke un audio dans le cache"""
        cache_key = self._get_cache_key(text, voice, engine)

        async with self._lock:
            # Vérifier la taille du cache
            await self._enforce_size_limit(len(audio_data))

            # Déterminer l'extension selon le moteur
            ext = ".mp3" if engine == "edge-tts" else ".wav"
            file_path = self.cache_dir / f"{cache_key}{ext}"

            # Écrire le fichier
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(audio_data)

            # Créer l'entrée
            entry = CacheEntry(
                text_hash=cache_key,
                voice=voice,
                engine=engine,
                file_path=str(file_path),
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=1,
                size_bytes=len(audio_data)
            )

            self.entries[cache_key] = entry
            await self._save_index()

            return str(file_path)

    async def _enforce_size_limit(self, new_size: int):
        """Applique la limite de taille du cache (LRU)"""
        total_size = sum(e.size_bytes for e in self.entries.values())

        while total_size + new_size > self.max_size_bytes and self.entries:
            # Trouver l'entrée la moins récemment utilisée
            lru_key = min(self.entries.keys(),
                         key=lambda k: self.entries[k].last_accessed)
            lru_entry = self.entries[lru_key]

            # Supprimer le fichier
            try:
                await aiofiles.os.remove(lru_entry.file_path)
            except Exception:
                pass

            total_size -= lru_entry.size_bytes
            del self.entries[lru_key]

    async def clear(self):
        """Vide le cache"""
        async with self._lock:
            for entry in self.entries.values():
                try:
                    await aiofiles.os.remove(entry.file_path)
                except Exception:
                    pass

            self.entries = {}
            await self._save_index()

    async def get_stats(self) -> dict:
        """Retourne les statistiques du cache"""
        total_size = sum(e.size_bytes for e in self.entries.values())
        total_accesses = sum(e.access_count for e in self.entries.values())

        return {
            "entries": len(self.entries),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_size_mb": round(self.max_size_bytes / (1024 * 1024), 2),
            "total_accesses": total_accesses,
            "hit_rate": "N/A"  # Would need to track misses
        }

    def is_preloadable(self, text: str) -> bool:
        """Vérifie si un texte fait partie des phrases pré-cachées"""
        return text in self.preload_phrases
