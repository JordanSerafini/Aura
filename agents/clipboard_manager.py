#!/usr/bin/env python3
"""
AURA-OS Agent: Clipboard Manager
Team: PC-Admin
Description: Historique presse-papiers intelligent
"""
import argparse, subprocess, json
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path.home() / ".aura" / "clipboard_history.json"
MAX_HISTORY = 50

def get_clipboard():
    try:
        r = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=2)
        return r.stdout if r.returncode == 0 else None
    except: return None

def set_clipboard(text):
    try:
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, text=True)
        p.communicate(input=text)
        return p.returncode == 0
    except: return False

def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []

def save_history(history):
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history[-MAX_HISTORY:], indent=2, ensure_ascii=False))

def add_entry(text):
    if not text or not text.strip(): return
    history = load_history()
    entry = {"text": text[:1000], "time": datetime.now().isoformat()}
    if not history or history[-1]["text"] != entry["text"]:
        history.append(entry)
        save_history(history)

def main():
    parser = argparse.ArgumentParser(description="Clipboard Manager Aura-OS")
    parser.add_argument("command", nargs="?", default="show", choices=["show", "history", "copy", "paste", "clear", "search"])
    parser.add_argument("text", nargs="?")
    parser.add_argument("--index", "-i", type=int)
    parser.add_argument("--limit", "-l", type=int, default=10)
    args = parser.parse_args()

    if args.command == "show":
        c = get_clipboard()
        print(f"📋 {c[:200]}..." if c and len(c) > 200 else f"📋 {c}" if c else "📋 Vide")

    elif args.command == "history":
        for i, e in enumerate(load_history()[-args.limit:]):
            print(f"  {i}: {e['text'][:50].replace(chr(10), '↵')}...")

    elif args.command == "copy" and args.text:
        set_clipboard(args.text)
        add_entry(args.text)
        print(f"✅ Copié")

    elif args.command == "paste":
        if args.index is not None:
            h = load_history()
            if 0 <= args.index < len(h):
                set_clipboard(h[args.index]["text"])
                print("✅ Restauré")
        else:
            print(get_clipboard() or "")

    elif args.command == "clear":
        set_clipboard("")
        print("✅ Vidé")

    elif args.command == "search" and args.text:
        for e in load_history():
            if args.text.lower() in e["text"].lower():
                print(f"  • {e['text'][:60]}...")

if __name__ == "__main__":
    main()
