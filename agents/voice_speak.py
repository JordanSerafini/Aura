#!/usr/bin/env python3
"""
AURA-OS Agent: Voice Speaker
Team: Vocal-UI
Description: Synthèse vocale via Edge-TTS (Microsoft) avec fallback Piper
"""

import argparse
import subprocess
import sys
import os
import tempfile
from pathlib import Path

# Voix Edge-TTS disponibles
EDGE_VOICES = {
    "henri": "fr-FR-HenriNeural",
    "denise": "fr-FR-DeniseNeural",
    "eloise": "fr-FR-EloiseNeural",
    "remy": "fr-FR-RemyMultilingualNeural",
    "vivienne": "fr-FR-VivienneMultilingualNeural"
}

DEFAULT_VOICE = "henri"
DEFAULT_RATE = "+20%"

# Config Piper (fallback)
VOICE_DIR = Path.home() / ".aura" / "voice"
PIPER_BIN = VOICE_DIR / "piper" / "piper"


def speak_edge(text: str, voice: str = DEFAULT_VOICE, rate: str = DEFAULT_RATE) -> bool:
    """Synthèse vocale via Edge-TTS."""
    voice_id = EDGE_VOICES.get(voice, EDGE_VOICES[DEFAULT_VOICE])

    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            temp_file = f.name

        cmd = [
            "edge-tts",
            "--voice", voice_id,
            "--rate", rate,
            "--text", text,
            "--write-media", temp_file
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return False

        play_cmd = ["mpv", "--no-video", "--really-quiet", temp_file]
        subprocess.run(play_cmd, capture_output=True, timeout=60)

        os.unlink(temp_file)
        return True

    except Exception:
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.unlink(temp_file)
        return False


def speak_piper(text: str, voice: str = "upmc", speed: float = 0.8) -> bool:
    """Fallback: Synthèse vocale via Piper (offline)."""
    piper_voices = {
        "upmc": "fr_FR-upmc-medium.onnx",
        "gilles": "fr_FR-gilles-low.onnx",
        "tom": "fr_FR-tom-medium.onnx",
        "siwis": "fr_FR-siwis-low.onnx"
    }

    model_file = piper_voices.get(voice, piper_voices["upmc"])
    model_path = VOICE_DIR / model_file

    if not PIPER_BIN.exists() or not model_path.exists():
        return False

    env = os.environ.copy()
    lib_path = str(VOICE_DIR / "piper")
    env["LD_LIBRARY_PATH"] = f"{lib_path}:{env.get('LD_LIBRARY_PATH', '')}"

    try:
        piper_cmd = [str(PIPER_BIN), "--model", str(model_path), "--length_scale", str(speed), "--output_raw"]
        aplay_cmd = ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-q"]

        piper_proc = subprocess.Popen(piper_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        aplay_proc = subprocess.Popen(aplay_cmd, stdin=piper_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        piper_proc.stdin.write(text.encode('utf-8'))
        piper_proc.stdin.close()
        piper_proc.stdout.close()
        aplay_proc.wait()
        piper_proc.wait()
        return True
    except Exception:
        return False


def speak(text: str, voice: str = DEFAULT_VOICE, rate: str = DEFAULT_RATE, use_piper: bool = False, silent: bool = False) -> bool:
    """Synthèse vocale avec fallback automatique."""
    if not text.strip():
        return True

    success = False
    if use_piper:
        success = speak_piper(text, voice="upmc")
    else:
        success = speak_edge(text, voice, rate)
        if not success:
            success = speak_piper(text, voice="upmc")

    if not silent:
        icon = "🔊" if success else "🔇"
        print(f"{icon} [{voice}] {text[:50]}{'...' if len(text) > 50 else ''}")

    return success


def main():
    parser = argparse.ArgumentParser(description="AURA-OS Voice Speaker")
    parser.add_argument("text", nargs="?", help="Texte à synthétiser")
    parser.add_argument("--voice", "-v", choices=list(EDGE_VOICES.keys()), default=DEFAULT_VOICE)
    parser.add_argument("--rate", "-r", default=DEFAULT_RATE)
    parser.add_argument("--piper", "-p", action="store_true")
    parser.add_argument("--silent", "-s", action="store_true")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--list", "-l", action="store_true")

    args = parser.parse_args()

    if args.list:
        print("Voix: henri, denise, eloise, remy, vivienne")
        return

    if args.stdin:
        text = sys.stdin.read().strip()
    elif args.text:
        text = args.text
    else:
        parser.error("Texte requis")
        return

    success = speak(text, voice=args.voice, rate=args.rate, use_piper=args.piper, silent=args.silent)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
