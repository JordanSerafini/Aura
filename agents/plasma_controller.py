#!/usr/bin/env python3
"""
AURA-OS Agent: Plasma Controller
Team: PC-Admin
Description: Contrôle des fenêtres et workspaces KDE Plasma
"""
import argparse, subprocess, json, re

def run_qdbus(args):
    """Exécute une commande qdbus"""
    try:
        result = subprocess.run(["qdbus"] + args, capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except: return ""

def run_kwin(method, *args):
    """Appelle une méthode KWin"""
    cmd = ["qdbus", "org.kde.KWin", "/KWin", method] + list(args)
    return run_qdbus(cmd[1:])

def get_windows():
    """Liste toutes les fenêtres"""
    windows = []
    try:
        out = subprocess.run(["wmctrl", "-l", "-p"], capture_output=True, text=True).stdout
        for line in out.strip().split('\n'):
            if line:
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    windows.append({
                        "id": parts[0],
                        "desktop": int(parts[1]),
                        "pid": parts[2],
                        "host": parts[3],
                        "title": parts[4] if len(parts) > 4 else ""
                    })
    except: pass
    return windows

def get_desktops():
    """Liste les bureaux virtuels"""
    try:
        out = subprocess.run(["wmctrl", "-d"], capture_output=True, text=True).stdout
        desktops = []
        for line in out.strip().split('\n'):
            parts = line.split()
            if parts:
                desktops.append({
                    "id": int(parts[0]),
                    "current": parts[1] == "*",
                    "name": parts[-1] if len(parts) > 8 else f"Desktop {parts[0]}"
                })
        return desktops
    except: return []

def focus_window(identifier):
    """Focus une fenêtre par titre ou ID"""
    windows = get_windows()
    for w in windows:
        if identifier.lower() in w["title"].lower() or identifier == w["id"]:
            subprocess.run(["wmctrl", "-i", "-a", w["id"]])
            return w
    return None

def close_window(identifier):
    """Ferme une fenêtre"""
    windows = get_windows()
    for w in windows:
        if identifier.lower() in w["title"].lower() or identifier == w["id"]:
            subprocess.run(["wmctrl", "-i", "-c", w["id"]])
            return w
    return None

def switch_desktop(num):
    """Change de bureau virtuel"""
    subprocess.run(["wmctrl", "-s", str(num)])

def tile_windows(layout="side"):
    """Arrange les fenêtres (basique)"""
    # Utilise les raccourcis KWin
    if layout == "left":
        subprocess.run(["qdbus", "org.kde.kglobalaccel", "/component/kwin", "invokeShortcut", "Window Quick Tile Left"])
    elif layout == "right":
        subprocess.run(["qdbus", "org.kde.kglobalaccel", "/component/kwin", "invokeShortcut", "Window Quick Tile Right"])
    elif layout == "maximize":
        subprocess.run(["qdbus", "org.kde.kglobalaccel", "/component/kwin", "invokeShortcut", "Window Maximize"])

def main():
    parser = argparse.ArgumentParser(description="Plasma Controller Aura-OS")
    parser.add_argument("command", nargs="?", default="list",
                       choices=["list", "desktops", "focus", "close", "switch", "tile", "minimize-all"])
    parser.add_argument("target", nargs="?", help="Fenêtre ou desktop cible")
    parser.add_argument("--format", "-f", default="text", choices=["text", "json"])
    args = parser.parse_args()

    if args.command == "list":
        windows = get_windows()
        if args.format == "json":
            print(json.dumps(windows, indent=2))
        else:
            print(f"\n🪟 {len(windows)} fenêtres ouvertes:")
            for w in windows:
                desktop = f"[{w['desktop']}]" if w['desktop'] >= 0 else "[all]"
                print(f"  {desktop} {w['title'][:50]}")

    elif args.command == "desktops":
        desktops = get_desktops()
        if args.format == "json":
            print(json.dumps(desktops, indent=2))
        else:
            print("\n🖥️ Bureaux virtuels:")
            for d in desktops:
                current = "→" if d["current"] else " "
                print(f"  {current} {d['id']}: {d['name']}")

    elif args.command == "focus" and args.target:
        w = focus_window(args.target)
        if w: print(f"✅ Focus: {w['title'][:40]}")
        else: print(f"❌ Fenêtre non trouvée: {args.target}")

    elif args.command == "close" and args.target:
        w = close_window(args.target)
        if w: print(f"✅ Fermé: {w['title'][:40]}")
        else: print(f"❌ Fenêtre non trouvée: {args.target}")

    elif args.command == "switch" and args.target:
        switch_desktop(int(args.target))
        print(f"✅ Basculé vers desktop {args.target}")

    elif args.command == "tile" and args.target:
        tile_windows(args.target)
        print(f"✅ Tile: {args.target}")

    elif args.command == "minimize-all":
        subprocess.run(["qdbus", "org.kde.kglobalaccel", "/component/kwin", "invokeShortcut", "MinimizeAll"])
        print("✅ Toutes les fenêtres minimisées")

if __name__ == "__main__":
    main()
