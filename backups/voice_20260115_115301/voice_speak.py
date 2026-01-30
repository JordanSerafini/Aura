#!/usr/bin/env python3
"""
AURA-OS Agent: Voice Speaker (Edge-TTS)
Team: Vocal-UI
Description: Synthèse vocale via Microsoft Edge-TTS - voix naturelles
Backup Piper: voice_speak_piper.py
"""

import argparse
import subprocess
import tempfile
import os
from pathlib import Path

# Configuration
EDGE_TTS_BIN = Path.home() / ".local" / "bin" / "edge-tts"
DEFAULT_VOICE = "fr-FR-HenriNeural"
DEFAULT_RATE = "+20%"  # Vitesse optimale

# Voix disponibles
VOICES = {
    "henri": "fr-FR-HenriNeural",
    "denise": "fr-FR-DeniseNeural",
    "eloise": "fr-FR-EloiseNeural",
    "remy": "fr-FR-RemyMultilingualNeural",
    "vivienne": "fr-FR-VivienneMultilingualNeural",
}

VOICE_INFO = {
    "henri": "Masculine, naturelle",
    "denise": "Féminine, chaleureuse",
    "eloise": "Féminine, douce",
    "remy": "Masculine, multilingue",
    "vivienne": "Féminine, multilingue",
}

def speak(text: str, voice: str = "henri", rate: str = DEFAULT_RATE, silent: bool = False):
    """Synthétise et joue un texte avec Edge-TTS."""

    voice_id = VOICES.get(voice, VOICES["henri"])

    if not EDGE_TTS_BIN.exists():
        print(f"❌ edge-tts non trouvé: {EDGE_TTS_BIN}")
        return False

    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        # Générer l'audio avec edge-tts
        cmd_tts = [
            str(EDGE_TTS_BIN),
            "--voice", voice_id,
            "--rate", rate,
            "--text", text,
            "--write-media", tmp_path
        ]

        result = subprocess.run(
            cmd_tts,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"❌ Erreur edge-tts: {result.stderr}")
            return False

        # Jouer l'audio
        subprocess.run(
            ["mpv", "--no-video", "--really-quiet", tmp_path],
            capture_output=True,
            timeout=60
        )

        # Nettoyer
        os.unlink(tmp_path)

        if not silent:
            print(f"🔊 [{voice}] {text[:50]}{'...' if len(text) > 50 else ''}")

        return True

    except subprocess.TimeoutExpired:
        print("❌ Timeout synthèse vocale")
        return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def list_voices():
    """Affiche les voix disponibles."""
    print("🎙️ Voix Edge-TTS disponibles:\n")
    for key, info in VOICE_INFO.items():
        marker = " (défaut)" if key == "henri" else ""
        print(f"  {key:12} - {info}{marker}")

def main():
    parser = argparse.ArgumentParser(description="AURA-OS Voice Agent (Edge-TTS)")
    parser.add_argument("text", nargs="?", help="Texte à synthétiser")
    parser.add_argument("--voice", "-v", choices=list(VOICES.keys()), default="henri",
                        help="Voix à utiliser (default: henri)")
    parser.add_argument("--rate", "-r", default=DEFAULT_RATE,
                        help="Vitesse: -50%% à +100%% (default: +10%%)")
    parser.add_argument("--silent", "-s", action="store_true",
                        help="Mode silencieux (pas d'output console)")
    parser.add_argument("--stdin", action="store_true",
                        help="Lire le texte depuis stdin")
    parser.add_argument("--list", "-l", action="store_true",
                        help="Lister les voix disponibles")
    parser.add_argument("--piper", action="store_true",
                        help="Utiliser Piper (backup) au lieu de Edge-TTS")

    args = parser.parse_args()

    if args.list:
        list_voices()
        return

    if args.piper:
        # Rediriger vers le backup Piper
        import sys
        piper_script = Path(__file__).parent / "voice_speak_piper.py"
        os.execv(sys.executable, [sys.executable, str(piper_script)] + sys.argv[1:])

    if args.stdin:
        import sys
        text = sys.stdin.read().strip()
    elif args.text:
        text = args.text
    else:
        parser.error("Texte requis (argument ou --stdin)")
        return

    success = speak(text, voice=args.voice, rate=args.rate, silent=args.silent)
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
