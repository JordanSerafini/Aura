#!/usr/bin/env python3
"""
AURA-OS Agent: File Organizer
Team: PC-Admin
Description: Rangement intelligent des téléchargements
"""
import argparse, shutil
from pathlib import Path

DOWNLOADS = Path.home() / "Downloads"
RULES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"],
    "Videos": [".mp4", ".mkv", ".avi", ".mov", ".webm"],
    "Music": [".mp3", ".wav", ".flac", ".ogg", ".m4a"],
    "Documents": [".pdf", ".doc", ".docx", ".odt", ".txt", ".xls", ".xlsx"],
    "Archives": [".zip", ".tar", ".gz", ".rar", ".7z"],
    "Code": [".py", ".js", ".ts", ".html", ".css", ".json", ".sh"],
    "Apps": [".deb", ".AppImage", ".flatpakref"],
}

def get_cat(f):
    ext = f.suffix.lower()
    for cat, exts in RULES.items():
        if ext in exts: return cat
    return None

def scan():
    res = {"to_organize": [], "unknown": []}
    for f in DOWNLOADS.iterdir():
        if f.is_file():
            cat = get_cat(f)
            if cat: res["to_organize"].append((f.name, cat))
            else: res["unknown"].append(f.name)
    return res

def organize(dry=False):
    moved = 0
    for f in DOWNLOADS.iterdir():
        if f.is_file():
            cat = get_cat(f)
            if cat:
                dest = DOWNLOADS / cat
                dest.mkdir(exist_ok=True)
                if not (dest / f.name).exists():
                    if dry: print(f"  → {f.name} → {cat}/")
                    else: shutil.move(str(f), str(dest / f.name))
                    moved += 1
    return moved

def main():
    parser = argparse.ArgumentParser(description="File Organizer Aura-OS")
    parser.add_argument("command", nargs="?", default="scan", choices=["scan", "organize", "rules"])
    parser.add_argument("--dry-run", "-n", action="store_true")
    args = parser.parse_args()

    if args.command == "scan":
        r = scan()
        print(f"📁 {len(r['to_organize'])} fichiers à ranger, {len(r['unknown'])} non classés")
        cats = {}
        for name, cat in r["to_organize"]:
            cats[cat] = cats.get(cat, 0) + 1
        for cat, n in cats.items(): print(f"  • {cat}: {n}")

    elif args.command == "organize":
        m = organize(dry=args.dry_run)
        print(f"✅ {m} fichiers {'à déplacer' if args.dry_run else 'déplacés'}")

    elif args.command == "rules":
        for cat, exts in RULES.items(): print(f"  {cat}: {', '.join(exts)}")

if __name__ == "__main__":
    main()
