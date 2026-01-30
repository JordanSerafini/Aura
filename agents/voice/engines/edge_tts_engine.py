"""
AURA-OS Edge TTS Engine
Moteur TTS utilisant Microsoft Edge TTS avec streaming
"""

import asyncio
import tempfile
import os
from pathlib import Path
from typing import AsyncIterator
import subprocess
import shutil

from .base import VoiceEngine, VoiceConfig, TTSRequest, TTSResult, Emotion


class EdgeTTSEngine(VoiceEngine):
    """Moteur TTS basé sur Edge-TTS avec support streaming"""

    name = "edge-tts"
    supports_streaming = True
    supports_ssml = True
    supports_emotions = True
    requires_internet = True

    # Mapping émotions vers styles SSML
    EMOTION_STYLES = {
        Emotion.NEUTRAL: "",
        Emotion.HAPPY: "cheerful",
        Emotion.SAD: "sad",
        Emotion.URGENT: "serious",
        Emotion.CALM: "calm",
        Emotion.EXCITED: "excited",
    }

    def __init__(self):
        super().__init__()
        self.edge_tts_bin = Path.home() / ".local" / "bin" / "edge-tts"
        self.default_voice = "henri"
        self.default_rate = "+20%"

        # Voix françaises disponibles
        self.voices = {
            "henri": VoiceConfig(
                voice_id="fr-FR-HenriNeural",
                name="henri",
                language="fr-FR",
                gender="male",
                description="Masculine, naturelle",
                rate="+20%"
            ),
            "denise": VoiceConfig(
                voice_id="fr-FR-DeniseNeural",
                name="denise",
                language="fr-FR",
                gender="female",
                description="Féminine, chaleureuse",
                rate="+20%"
            ),
            "eloise": VoiceConfig(
                voice_id="fr-FR-EloiseNeural",
                name="eloise",
                language="fr-FR",
                gender="female",
                description="Féminine, douce",
                rate="+10%"
            ),
            "remy": VoiceConfig(
                voice_id="fr-FR-RemyMultilingualNeural",
                name="remy",
                language="fr-FR",
                gender="male",
                description="Masculine, multilingue",
                rate="+20%"
            ),
            "vivienne": VoiceConfig(
                voice_id="fr-FR-VivienneMultilingualNeural",
                name="vivienne",
                language="fr-FR",
                gender="female",
                description="Féminine, multilingue",
                rate="+20%"
            ),
        }

    async def initialize(self) -> bool:
        """Initialise le moteur Edge-TTS"""
        try:
            # Vérifier si edge-tts est installé
            if not self.edge_tts_bin.exists():
                # Essayer de le trouver dans PATH
                edge_path = shutil.which("edge-tts")
                if edge_path:
                    self.edge_tts_bin = Path(edge_path)
                else:
                    return False

            self._initialized = True
            return True
        except Exception:
            return False

    def is_available(self) -> bool:
        """Vérifie si Edge-TTS est disponible"""
        return self.edge_tts_bin.exists() or shutil.which("edge-tts") is not None

    def get_voices(self) -> list[VoiceConfig]:
        """Retourne la liste des voix disponibles"""
        return list(self.voices.values())

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Synthétise le texte en audio"""
        voice_name = request.voice or self.default_voice
        voice = self.voices.get(voice_name, self.voices[self.default_voice])
        rate = request.rate or voice.rate or self.default_rate

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name

            # Construire la commande
            cmd = [
                str(self.edge_tts_bin),
                "--voice", voice.voice_id,
                "--rate", rate,
                "--text", request.text,
                "--write-media", tmp_path
            ]

            # Exécuter edge-tts
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                return TTSResult(
                    success=False,
                    error=f"Edge-TTS error: {stderr.decode()}"
                )

            # Lire le fichier audio
            with open(tmp_path, 'rb') as f:
                audio_data = f.read()

            return TTSResult(
                success=True,
                audio_path=tmp_path,
                audio_data=audio_data,
                from_cache=False
            )

        except asyncio.TimeoutError:
            return TTSResult(success=False, error="Timeout Edge-TTS")
        except Exception as e:
            return TTSResult(success=False, error=str(e))

    async def stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        """Stream l'audio via edge-tts en temps réel"""
        voice_name = request.voice or self.default_voice
        voice = self.voices.get(voice_name, self.voices[self.default_voice])
        rate = request.rate or voice.rate or self.default_rate

        try:
            # edge-tts avec --write-media - on peut streamer le fichier
            # Pour un vrai streaming, on utilise edge-playback ou on lit progressivement
            cmd = [
                str(self.edge_tts_bin),
                "--voice", voice.voice_id,
                "--rate", rate,
                "--text", request.text,
                "--write-media", "/dev/stdout"
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Streamer les chunks
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                yield chunk

            await proc.wait()

        except Exception as e:
            raise RuntimeError(f"Streaming error: {e}")

    def apply_emotion(self, text: str, emotion: Emotion) -> str:
        """Applique une émotion via les paramètres de voix"""
        # Edge-TTS ne supporte pas directement les émotions
        # On peut simuler avec le rate/pitch
        emotion_adjustments = {
            Emotion.HAPPY: ("+10%", "+5Hz"),
            Emotion.SAD: ("-10%", "-5Hz"),
            Emotion.URGENT: ("+30%", "+0Hz"),
            Emotion.CALM: ("-15%", "-3Hz"),
            Emotion.EXCITED: ("+25%", "+10Hz"),
        }
        return text  # Pour l'instant, on retourne tel quel

    def text_to_ssml(self, text: str, emotion: Emotion = Emotion.NEUTRAL) -> str:
        """Convertit le texte en SSML pour Edge-TTS"""
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Ajouter des breaks pour les pauses naturelles
        ssml = escaped.replace(". ", '.<break time="300ms"/> ')
        ssml = ssml.replace("! ", '!<break time="300ms"/> ')
        ssml = ssml.replace("? ", '?<break time="400ms"/> ')

        return f'<speak>{ssml}</speak>'
