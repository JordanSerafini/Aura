"""
AURA-OS Voice Engine Base Class
Classe abstraite pour tous les moteurs TTS
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator
import asyncio


class Emotion(Enum):
    """Émotions supportées pour le TTS"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    URGENT = "urgent"
    CALM = "calm"
    EXCITED = "excited"


class Priority(Enum):
    """Priorités des messages vocaux"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class VoiceConfig:
    """Configuration d'une voix"""
    voice_id: str
    name: str
    language: str = "fr-FR"
    gender: str = "male"
    description: str = ""
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"


@dataclass
class TTSRequest:
    """Requête de synthèse vocale"""
    text: str
    voice: str | None = None
    emotion: Emotion = Emotion.NEUTRAL
    priority: Priority = Priority.NORMAL
    rate: str | None = None
    ssml: bool = False
    cache_key: str | None = None
    output_device: str | None = None  # None = default


@dataclass
class TTSResult:
    """Résultat de synthèse vocale"""
    success: bool
    audio_path: str | None = None
    audio_data: bytes | None = None
    duration_ms: int = 0
    from_cache: bool = False
    error: str | None = None


class VoiceEngine(ABC):
    """Classe de base abstraite pour les moteurs TTS"""

    name: str = "base"
    supports_streaming: bool = False
    supports_ssml: bool = False
    supports_emotions: bool = False
    requires_internet: bool = False

    def __init__(self):
        self.voices: dict[str, VoiceConfig] = {}
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialise le moteur TTS"""
        pass

    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Synthétise le texte en audio"""
        pass

    @abstractmethod
    async def stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        """Stream l'audio chunk par chunk (si supporté)"""
        pass

    @abstractmethod
    def get_voices(self) -> list[VoiceConfig]:
        """Retourne la liste des voix disponibles"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Vérifie si le moteur est disponible"""
        pass

    def get_voice(self, voice_name: str) -> VoiceConfig | None:
        """Récupère une voix par son nom"""
        return self.voices.get(voice_name)

    def apply_emotion(self, text: str, emotion: Emotion) -> str:
        """Applique une émotion au texte (override dans les sous-classes)"""
        return text

    def text_to_ssml(self, text: str, emotion: Emotion = Emotion.NEUTRAL) -> str:
        """Convertit le texte en SSML"""
        # Implémentation basique, peut être override
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<speak>{escaped}</speak>'

    async def cleanup(self):
        """Nettoie les ressources"""
        pass
