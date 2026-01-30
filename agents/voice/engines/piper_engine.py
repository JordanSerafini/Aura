"""
AURA-OS Piper TTS Engine
Moteur TTS local basé sur Piper (100% offline)
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator

from .base import VoiceEngine, VoiceConfig, TTSRequest, TTSResult, Emotion


class PiperEngine(VoiceEngine):
    """Moteur TTS basé sur Piper (offline)"""

    name = "piper"
    supports_streaming = True
    supports_ssml = False
    supports_emotions = False
    requires_internet = False

    def __init__(self):
        super().__init__()
        self.voice_dir = Path.home() / ".aura" / "voice"
        self.piper_bin = self.voice_dir / "piper" / "piper"
        self.default_voice = "upmc"
        self.default_speed = 0.80
        self.sample_rate = 22050

        # Voix Piper françaises disponibles
        self.voices = {
            "upmc": VoiceConfig(
                voice_id="fr_FR-upmc-medium.onnx",
                name="upmc",
                language="fr-FR",
                gender="male",
                description="Voix UPMC medium quality"
            ),
            "gilles": VoiceConfig(
                voice_id="fr_FR-gilles-low.onnx",
                name="gilles",
                language="fr-FR",
                gender="male",
                description="Voix Gilles low quality"
            ),
            "tom": VoiceConfig(
                voice_id="fr_FR-tom-medium.onnx",
                name="tom",
                language="fr-FR",
                gender="male",
                description="Voix Tom medium quality"
            ),
            "siwis": VoiceConfig(
                voice_id="fr_FR-siwis-low.onnx",
                name="siwis",
                language="fr-FR",
                gender="female",
                description="Voix Siwis low quality"
            ),
        }

    async def initialize(self) -> bool:
        """Initialise le moteur Piper"""
        try:
            if not self.piper_bin.exists():
                return False

            # Vérifier qu'au moins un modèle existe
            for voice in self.voices.values():
                model_path = self.voice_dir / voice.voice_id
                if model_path.exists():
                    self._initialized = True
                    return True

            return False
        except Exception:
            return False

    def is_available(self) -> bool:
        """Vérifie si Piper est disponible"""
        if not self.piper_bin.exists():
            return False

        # Vérifier au moins un modèle
        for voice in self.voices.values():
            if (self.voice_dir / voice.voice_id).exists():
                return True
        return False

    def get_voices(self) -> list[VoiceConfig]:
        """Retourne les voix disponibles (modèles présents)"""
        available = []
        for voice in self.voices.values():
            if (self.voice_dir / voice.voice_id).exists():
                available.append(voice)
        return available

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Synthétise le texte en audio avec Piper"""
        voice_name = request.voice or self.default_voice
        voice = self.voices.get(voice_name, self.voices[self.default_voice])
        model_path = self.voice_dir / voice.voice_id

        if not model_path.exists():
            return TTSResult(success=False, error=f"Modèle non trouvé: {model_path}")

        try:
            # Configurer l'environnement
            env = os.environ.copy()
            lib_path = str(self.voice_dir / "piper")
            env["LD_LIBRARY_PATH"] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            # Commande Piper
            cmd = [
                str(self.piper_bin),
                "--model", str(model_path),
                "--length_scale", str(self.default_speed),
                "--output_file", tmp_path
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=request.text.encode('utf-8')),
                timeout=30
            )

            if proc.returncode != 0:
                return TTSResult(success=False, error=f"Piper error: {stderr.decode()}")

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
            return TTSResult(success=False, error="Timeout Piper")
        except Exception as e:
            return TTSResult(success=False, error=str(e))

    async def stream(self, request: TTSRequest) -> AsyncIterator[bytes]:
        """Stream l'audio depuis Piper en temps réel"""
        voice_name = request.voice or self.default_voice
        voice = self.voices.get(voice_name, self.voices[self.default_voice])
        model_path = self.voice_dir / voice.voice_id

        if not model_path.exists():
            raise RuntimeError(f"Modèle non trouvé: {model_path}")

        env = os.environ.copy()
        lib_path = str(self.voice_dir / "piper")
        env["LD_LIBRARY_PATH"] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"

        cmd = [
            str(self.piper_bin),
            "--model", str(model_path),
            "--length_scale", str(self.default_speed),
            "--output_raw"
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        # Envoyer le texte
        proc.stdin.write(request.text.encode('utf-8'))
        await proc.stdin.drain()
        proc.stdin.close()

        # Streamer les chunks audio raw
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            yield chunk

        await proc.wait()
