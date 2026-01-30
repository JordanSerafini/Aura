#!/usr/bin/env python3
"""
AURA-OS Agent: Screenshot OCR
Team: Info-Data
Description: Capture écran et extraction texte OCR
"""
import argparse, subprocess, tempfile
from datetime import datetime
from pathlib import Path

SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"

def screenshot(region=False, output=None):
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    out = output or SCREENSHOTS_DIR / f"shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    cmd = ["spectacle", "-b", "-n", "-o", str(out)]
    cmd.append("-r" if region else "-f")
    try:
        subprocess.run(cmd, timeout=30)
        return out if out.exists() else None
    except:
        try:
            subprocess.run(["scrot", "-s" if region else "", str(out)], timeout=30)
            return out if out.exists() else None
        except: return None

def ocr(image_path, lang="fra"):
    try:
        r = subprocess.run(["tesseract", str(image_path), "stdout", "-l", lang],
                          capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except FileNotFoundError:
        print("❌ sudo apt install tesseract-ocr tesseract-ocr-fra")
        return None

def to_clipboard(text):
    try:
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, text=True)
        p.communicate(input=text)
    except: pass

def main():
    parser = argparse.ArgumentParser(description="Screenshot OCR Aura-OS")
    parser.add_argument("command", nargs="?", default="capture", choices=["capture", "ocr", "capture-ocr", "list"])
    parser.add_argument("--region", "-r", action="store_true")
    parser.add_argument("--file", "-f")
    parser.add_argument("--lang", "-l", default="fra")
    parser.add_argument("--copy", "-c", action="store_true")
    args = parser.parse_args()

    if args.command == "capture":
        s = screenshot(region=args.region)
        print(f"✅ {s}" if s else "❌ Échec")

    elif args.command == "ocr" and args.file:
        text = ocr(Path(args.file), args.lang)
        if text:
            print(text)
            if args.copy: to_clipboard(text)

    elif args.command == "capture-ocr":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            s = screenshot(region=args.region, output=Path(tmp.name))
            if s:
                text = ocr(s, args.lang)
                if text:
                    print(text)
                    if args.copy: to_clipboard(text)
                Path(tmp.name).unlink()

    elif args.command == "list":
        for f in sorted(SCREENSHOTS_DIR.glob("*.png"), reverse=True)[:10]:
            print(f"  • {f.name}")

if __name__ == "__main__":
    main()
