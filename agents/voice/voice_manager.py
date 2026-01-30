#!/usr/bin/env python3
"""
AURA-OS Voice Manager v2.0
Orchestrateur principal du système de synthèse vocale

Features:
- Multi-engine (Edge-TTS, Piper, Kyutai)
- Streaming audio
- Cache intelligent
- Queue de messages avec priorités
- Contrôle émotionnel
- Support SSML
- Multi-output (casque/HP)
"""

import asyncio
import subprocess
import tempfile
import os
import argparse
from pathlib import Path
from enum import Enum

# Imports locaux
from engines.base import VoiceEngine, VoiceConfig, TTSRequest, TTSResult, Emotion, Priority
from engines.edge_tts_engine import EdgeTTSEngine
from engines.piper_engine import PiperEngine
from engines.cache import VoiceCache
from queue_manager import VoiceQueueManager, get_queue_manager



class OutputDevice(Enum):
    """Périphériques de sortie audio"""
    DEFAULT = "default"
    HEADPHONES = "headphones"
    SPEAKERS = "speakers"


class VoiceManager:
    """Gestionnaire principal de synthèse vocale"""

    def __init__(self):
        self.engines: dict[str, VoiceEngine] = {}
        self.cache: VoiceCache | None = None
        self.queue: VoiceQueueManager | None = None
        self.default_engine = "edge-tts"
        self.default_voice = "henri"
        self.output_device = OutputDevice.DEFAULT
        self._initialized = False

        # Mapping périphériques audio (à configurer selon le système)
        self._audio_sinks = {
            OutputDevice.DEFAULT: None,  # Utilise le défaut du système
            OutputDevice.HEADPHONES: None,  # À détecter dynamiquement
            OutputDevice.SPEAKERS: None,
        }

    async def initialize(self) -> bool:
        """Initialise tous les composants"""
        try:
            # Initialiser les moteurs
            edge_engine = EdgeTTSEngine()
            if await edge_engine.initialize():
                self.engines["edge-tts"] = edge_engine

            piper_engine = PiperEngine()
            if await piper_engine.initialize():
                self.engines["piper"] = piper_engine

            # Initialiser le cache
            self.cache = VoiceCache()
            await self.cache.initialize()

            # Initialiser la queue
            self.queue = get_queue_manager()
            self.queue.set_speak_callback(self._speak_internal)
            await self.queue.start()

            # Détecter les périphériques audio
            await self._detect_audio_devices()

            self._initialized = True
            return len(self.engines) > 0

        except Exception as e:
            print(f"Erreur initialisation: {e}")
            return False

    async def _detect_audio_devices(self):
        """Détecte les périphériques audio disponibles"""
        try:
            # Utiliser pactl pour lister les sinks
            result = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        sink_name = parts[1].lower()
                        if 'headphone' in sink_name or 'headset' in sink_name:
                            self._audio_sinks[OutputDevice.HEADPHONES] = parts[1]
                        elif 'speaker' in sink_name or 'analog' in sink_name:
                            self._audio_sinks[OutputDevice.SPEAKERS] = parts[1]

        except Exception:
            pass  # Garder les valeurs par défaut

    def get_engine(self, name: str | None = None) -> VoiceEngine | None:
        """Récupère un moteur par son nom"""
        if name is None:
            name = self.default_engine
        return self.engines.get(name)

    def list_engines(self) -> list[str]:
        """Liste les moteurs disponibles"""
        return list(self.engines.keys())

    def list_voices(self, engine: str | None = None) -> list[VoiceConfig]:
        """Liste toutes les voix disponibles"""
        voices = []
        engines_to_check = [self.engines[engine]] if engine else self.engines.values()

        for eng in engines_to_check:
            voices.extend(eng.get_voices())

        return voices

    async def speak(
        self,
        text: str,
        voice: str | None = None,
        engine: str | None = None,
        emotion: Emotion = Emotion.NEUTRAL,
        priority: Priority = Priority.NORMAL,
        use_cache: bool = True,
        use_queue: bool = True,
        output_device: OutputDevice | None = None,
        ssml: bool = False
    ) -> bool:
        """
        Synthétise et joue un texte.

        Args:
            text: Texte à synthétiser
            voice: Nom de la voix (défaut: henri)
            engine: Moteur à utiliser (défaut: edge-tts)
            emotion: Émotion à appliquer
            priority: Priorité du message
            use_cache: Utiliser le cache
            use_queue: Passer par la queue
            output_device: Périphérique de sortie
            ssml: Le texte est du SSML
        """
        if not self._initialized:
            await self.initialize()

        voice = voice or self.default_voice
        engine_name = engine or self.default_engine

        if use_queue and self.queue:
            # Passer par la queue
            await self.queue.enqueue(
                text=text,
                voice=voice,
                priority=priority
            )
            return True
        else:
            # Synthèse directe
            return await self._speak_internal(text, voice, engine_name, emotion, use_cache, output_device)

    async def _speak_internal(
        self,
        text: str,
        voice: str | None = None,
        engine_name: str | None = None,
        emotion: Emotion = Emotion.NEUTRAL,
        use_cache: bool = True,
        output_device: OutputDevice | None = None
    ) -> bool:
        """Synthèse interne (appelée par la queue ou directement)"""
        voice = voice or self.default_voice
        engine_name = engine_name or self.default_engine
        output_device = output_device or self.output_device

        # Vérifier le cache d'abord
        if use_cache and self.cache:
            cached_audio = await self.cache.get(text, voice, engine_name)
            if cached_audio:
                return await self._play_audio(cached_audio, engine_name, output_device)

        # Obtenir le moteur
        engine = self.get_engine(engine_name)
        if not engine:
            print(f"Moteur {engine_name} non disponible")
            return False

        # Créer la requête
        request = TTSRequest(
            text=text,
            voice=voice,
            emotion=emotion
        )

        # Synthétiser
        result = await engine.synthesize(request)

        if not result.success:
            print(f"Erreur synthèse: {result.error}")
            return False

        # Mettre en cache
        if use_cache and self.cache and result.audio_data:
            await self.cache.put(text, voice, engine_name, result.audio_data)

        # Jouer l'audio
        return await self._play_audio(result.audio_data, engine_name, output_device, result.audio_path)

    async def _play_audio(
        self,
        audio_data: bytes,
        engine_name: str,
        output_device: OutputDevice = OutputDevice.DEFAULT,
        audio_path: str | None = None
    ) -> bool:
        """Joue l'audio sur le périphérique spécifié"""
        try:
            # Créer un fichier temporaire si pas de path
            if not audio_path:
                ext = ".mp3" if engine_name == "edge-tts" else ".wav"
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(audio_data)
                    audio_path = tmp.name

            # Construire la commande mpv avec le sink audio
            cmd = ["mpv", "--no-video", "--really-quiet"]

            sink = self._audio_sinks.get(output_device)
            if sink:
                cmd.extend(["--audio-device", f"pulse/{sink}"])

            cmd.append(audio_path)

            # Jouer
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )

            await asyncio.wait_for(proc.wait(), timeout=60)

            # Nettoyer le fichier temporaire
            if audio_path and audio_path.startswith('/tmp'):
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass

            return True

        except Exception as e:
            print(f"Erreur lecture audio: {e}")
            return False

    async def speak_streaming(
        self,
        text: str,
        voice: str | None = None,
        engine: str | None = None
    ) -> bool:
        """Synthétise avec streaming (lecture pendant la génération)"""
        voice = voice or self.default_voice
        engine_name = engine or self.default_engine

        eng = self.get_engine(engine_name)
        if not eng or not eng.supports_streaming:
            # Fallback sur la méthode normale
            return await self.speak(text, voice, engine_name, use_queue=False)

        request = TTSRequest(text=text, voice=voice)

        try:
            # Déterminer le format selon le moteur
            if engine_name == "piper":
                # Piper output raw PCM
                aplay_cmd = ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-q"]
                proc = await asyncio.create_subprocess_exec(
                    *aplay_cmd,
                    stdin=asyncio.subprocess.PIPE
                )

                async for chunk in eng.stream(request):
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()

                proc.stdin.close()
                await proc.wait()

            else:
                # Edge-TTS output MP3 - utiliser mpv
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    async for chunk in eng.stream(request):
                        tmp.write(chunk)
                    tmp_path = tmp.name

                proc = await asyncio.create_subprocess_exec(
                    "mpv", "--no-video", "--really-quiet", tmp_path
                )
                await proc.wait()
                os.unlink(tmp_path)

            return True

        except Exception as e:
            print(f"Erreur streaming: {e}")
            return False

    def set_output_device(self, device: OutputDevice):
        """Change le périphérique de sortie par défaut"""
        self.output_device = device

    async def preload_cache(self):
        """Précharge le cache avec les phrases fréquentes"""
        if not self.cache:
            return

        engine = self.get_engine()
        if not engine:
            return

        for phrase in self.cache.preload_phrases:
            cached = await self.cache.get(phrase, self.default_voice, self.default_engine)
            if not cached:
                request = TTSRequest(text=phrase, voice=self.default_voice)
                result = await engine.synthesize(request)
                if result.success and result.audio_data:
                    await self.cache.put(
                        phrase,
                        self.default_voice,
                        self.default_engine,
                        result.audio_data
                    )

    async def get_stats(self) -> dict:
        """Retourne les statistiques du système"""
        stats = {
            "engines": self.list_engines(),
            "default_engine": self.default_engine,
            "default_voice": self.default_voice,
            "output_device": self.output_device.value,
        }

        if self.cache:
            stats["cache"] = await self.cache.get_stats()

        if self.queue:
            stats["queue"] = self.queue.get_stats()

        return stats

    async def cleanup(self):
        """Nettoie les ressources"""
        if self.queue:
            await self.queue.stop()

        for engine in self.engines.values():
            await engine.cleanup()


# Instance singleton
_manager: VoiceManager | None = None


def get_voice_manager() -> VoiceManager:
    """Retourne l'instance singleton du voice manager"""
    global _manager
    if _manager is None:
        _manager = VoiceManager()
    return _manager


async def speak(text: str, voice: str = "henri", **kwargs) -> bool:
    """Fonction helper pour synthèse rapide"""
    manager = get_voice_manager()
    if not manager._initialized:
        await manager.initialize()
    return await manager.speak(text, voice=voice, use_queue=False, **kwargs)


# ============================================================
# CLI
# ============================================================

async def main_async():
    parser = argparse.ArgumentParser(description="AURA-OS Voice Manager v2.0")
    parser.add_argument("text", nargs="?", help="Texte à synthétiser")
    parser.add_argument("--voice", "-v", default="henri", help="Voix à utiliser")
    parser.add_argument("--engine", "-e", choices=["edge-tts", "piper", "kyutai"],
                        default="edge-tts", help="Moteur TTS")
    parser.add_argument("--emotion", choices=["neutral", "happy", "sad", "urgent", "calm"],
                        default="neutral", help="Émotion")
    parser.add_argument("--priority", choices=["low", "normal", "high", "urgent"],
                        default="normal", help="Priorité")
    parser.add_argument("--output", "-o", choices=["default", "headphones", "speakers"],
                        default="default", help="Sortie audio")
    parser.add_argument("--no-cache", action="store_true", help="Désactiver le cache")
    parser.add_argument("--streaming", "-s", action="store_true", help="Mode streaming")
    parser.add_argument("--list-voices", "-l", action="store_true", help="Lister les voix")
    parser.add_argument("--list-engines", action="store_true", help="Lister les moteurs")
    parser.add_argument("--stats", action="store_true", help="Afficher les stats")
    parser.add_argument("--preload", action="store_true", help="Précharger le cache")
    parser.add_argument("--stdin", action="store_true", help="Lire depuis stdin")

    args = parser.parse_args()

    manager = get_voice_manager()
    await manager.initialize()

    if args.list_engines:
        print("Moteurs disponibles:")
        for eng in manager.list_engines():
            marker = " (défaut)" if eng == manager.default_engine else ""
            print(f"  - {eng}{marker}")
        return

    if args.list_voices:
        print("Voix disponibles:")
        for voice in manager.list_voices():
            print(f"  [{voice.name}] {voice.description} ({voice.language})")
        return

    if args.stats:
        import json
        stats = await manager.get_stats()
        print(json.dumps(stats, indent=2, default=str))
        return

    if args.preload:
        print("Préchargement du cache...")
        await manager.preload_cache()
        print("Cache préchargé.")
        return

    # Synthèse
    if args.stdin:
        import sys
        text = sys.stdin.read().strip()
    elif args.text:
        text = args.text
    else:
        parser.error("Texte requis (argument ou --stdin)")
        return

    emotion = Emotion[args.emotion.upper()]
    priority = Priority[args.priority.upper()]
    output_device = OutputDevice[args.output.upper()]

    if args.streaming:
        success = await manager.speak_streaming(text, args.voice, args.engine)
    else:
        success = await manager.speak(
            text,
            voice=args.voice,
            engine=args.engine,
            emotion=emotion,
            priority=priority,
            use_cache=not args.no_cache,
            use_queue=False,
            output_device=output_device
        )

    if success:
        print(f"🔊 [{args.voice}] {text[:50]}{'...' if len(text) > 50 else ''}")
    else:
        print("❌ Échec de la synthèse")

    await manager.cleanup()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
