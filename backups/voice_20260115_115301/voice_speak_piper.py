#!/usr/bin/env python3
"""
AURA-OS Agent: Voice Speaker
Team: Vocal-UI
Description: Synthèse vocale via Piper avec configuration centralisée
"""

import argparse
import subprocess
import os
from pathlib import Path

# Configuration vocale
VOICE_DIR = Path.home() / ".aura" / "voice"
PIPER_BIN = VOICE_DIR / "piper" / "piper"
DEFAULT_MODEL = VOICE_DIR / "fr_FR-upmc-medium.onnx"  # Voix UPMC
DEFAULT_SPEED = 0.80  # Vitesse légèrement accélérée

# Modèles disponibles
VOICES = {
    "upmc": "fr_FR-upmc-medium.onnx",
    "gilles": "fr_FR-gilles-low.onnx",
    "tom": "fr_FR-tom-medium.onnx",
    "siwis": "fr_FR-siwis-low.onnx"
}

def speak(text: str, voice: str = "upmc", speed: float = DEFAULT_SPEED, silent: bool = False):
    """Synthétise et joue un texte avec Piper."""

    model_file = VOICES.get(voice, VOICES["upmc"])
    model_path = VOICE_DIR / model_file

    if not model_path.exists():
        print(f"❌ Modèle vocal non trouvé: {model_path}")
        return False

    if not PIPER_BIN.exists():
        print(f"❌ Piper non trouvé: {PIPER_BIN}")
        return False

    # Configurer LD_LIBRARY_PATH
    env = os.environ.copy()
    lib_path = str(VOICE_DIR / "piper")
    env["LD_LIBRARY_PATH"] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"

    try:
        # Pipeline Piper -> aplay
        piper_cmd = [
            str(PIPER_BIN),
            "--model", str(model_path),
            "--length_scale", str(speed),
            "--output_raw"
        ]

        aplay_cmd = ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-q"]

        # Exécuter le pipeline
        piper_proc = subprocess.Popen(
            piper_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env
        )

        aplay_proc = subprocess.Popen(
            aplay_cmd,
            stdin=piper_proc.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        piper_proc.stdin.write(text.encode('utf-8'))
        piper_proc.stdin.close()
        piper_proc.stdout.close()
        aplay_proc.wait()
        piper_proc.wait()

        if not silent:
            print(f"🔊 [{voice}] {text[:50]}{'...' if len(text) > 50 else ''}")

        return True

    except Exception as e:
        print(f"❌ Erreur synthèse vocale: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="AURA-OS Voice Agent")
    parser.add_argument("text", nargs="?", help="Texte à synthétiser")
    parser.add_argument("--voice", choices=list(VOICES.keys()), default="upmc",
                        help="Voix à utiliser (default: upmc)")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED,
                        help="Vitesse (1.0=normal, >1=lent, <1=rapide)")
    parser.add_argument("--silent", action="store_true",
                        help="Mode silencieux (pas d'output console)")
    parser.add_argument("--stdin", action="store_true",
                        help="Lire le texte depuis stdin")

    args = parser.parse_args()

    if args.stdin:
        import sys
        text = sys.stdin.read().strip()
    elif args.text:
        text = args.text
    else:
        parser.error("Texte requis (argument ou --stdin)")
        return

    success = speak(text, voice=args.voice, speed=args.speed, silent=args.silent)
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
