#!/usr/bin/env python3
"""
AURA-OS Agent: App Installer
Team: PC-Admin
Description: Installation intelligente de paquets apt/flatpak/snap
"""
import argparse, subprocess, json, sys

def run_cmd(cmd, sudo=False):
    """Exécute une commande"""
    if sudo: cmd = ["sudo"] + cmd
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def search_apt(name):
    """Recherche dans apt"""
    ok, out = run_cmd(["apt-cache", "search", name])
    if ok:
        results = []
        for line in out.strip().split('\n')[:10]:
            if ' - ' in line:
                pkg, desc = line.split(' - ', 1)
                results.append({"name": pkg.strip(), "desc": desc.strip(), "source": "apt"})
        return results
    return []

def search_flatpak(name):
    """Recherche dans Flatpak"""
    ok, out = run_cmd(["flatpak", "search", name])
    if ok:
        results = []
        for line in out.strip().split('\n')[1:10]:
            parts = line.split('\t')
            if len(parts) >= 2:
                results.append({"name": parts[0].strip(), "desc": parts[1].strip() if len(parts) > 1 else "", "source": "flatpak"})
        return results
    return []

def search_snap(name):
    """Recherche dans Snap"""
    ok, out = run_cmd(["snap", "find", name])
    if ok:
        results = []
        for line in out.strip().split('\n')[1:10]:
            parts = line.split()
            if parts:
                results.append({"name": parts[0], "desc": " ".join(parts[3:]) if len(parts) > 3 else "", "source": "snap"})
        return results
    return []

def install(name, source="auto"):
    """Installe un paquet"""
    if source == "auto":
        # Essaie apt d'abord
        if search_apt(name):
            source = "apt"
        elif search_flatpak(name):
            source = "flatpak"
        elif search_snap(name):
            source = "snap"
        else:
            return False, "Paquet non trouvé"

    if source == "apt":
        return run_cmd(["apt", "install", "-y", name], sudo=True)
    elif source == "flatpak":
        return run_cmd(["flatpak", "install", "-y", name])
    elif source == "snap":
        return run_cmd(["snap", "install", name], sudo=True)
    return False, "Source inconnue"

def remove(name, source="auto"):
    """Supprime un paquet"""
    if source == "apt" or source == "auto":
        ok, out = run_cmd(["apt", "remove", "-y", name], sudo=True)
        if ok: return ok, out
    if source == "flatpak" or source == "auto":
        ok, out = run_cmd(["flatpak", "uninstall", "-y", name])
        if ok: return ok, out
    if source == "snap" or source == "auto":
        return run_cmd(["snap", "remove", name], sudo=True)
    return False, "Non trouvé"

def list_installed(source="all"):
    """Liste les paquets installés"""
    installed = []
    if source in ["all", "apt"]:
        ok, out = run_cmd(["dpkg", "--get-selections"])
        if ok:
            for line in out.split('\n')[:50]:
                if '\tinstall' in line:
                    installed.append({"name": line.split()[0], "source": "apt"})
    if source in ["all", "flatpak"]:
        ok, out = run_cmd(["flatpak", "list", "--app"])
        if ok:
            for line in out.strip().split('\n'):
                parts = line.split('\t')
                if parts: installed.append({"name": parts[0], "source": "flatpak"})
    if source in ["all", "snap"]:
        ok, out = run_cmd(["snap", "list"])
        if ok:
            for line in out.strip().split('\n')[1:]:
                parts = line.split()
                if parts: installed.append({"name": parts[0], "source": "snap"})
    return installed

def update_all():
    """Met à jour tous les gestionnaires"""
    results = []
    print("📦 Mise à jour apt...")
    ok, _ = run_cmd(["apt", "update"], sudo=True)
    if ok:
        ok, out = run_cmd(["apt", "upgrade", "-y"], sudo=True)
        results.append(("apt", ok))
    print("📦 Mise à jour flatpak...")
    ok, _ = run_cmd(["flatpak", "update", "-y"])
    results.append(("flatpak", ok))
    print("📦 Mise à jour snap...")
    ok, _ = run_cmd(["snap", "refresh"], sudo=True)
    results.append(("snap", ok))
    return results

def main():
    parser = argparse.ArgumentParser(description="App Installer Aura-OS")
    parser.add_argument("command", nargs="?", default="search",
                       choices=["search", "install", "remove", "list", "update"])
    parser.add_argument("package", nargs="?", help="Nom du paquet")
    parser.add_argument("--source", "-s", default="auto", choices=["auto", "apt", "flatpak", "snap", "all"])
    parser.add_argument("--format", "-f", default="text", choices=["text", "json"])
    args = parser.parse_args()

    if args.command == "search" and args.package:
        print(f"🔍 Recherche de '{args.package}'...")
        results = []
        if args.source in ["auto", "all", "apt"]: results += search_apt(args.package)
        if args.source in ["auto", "all", "flatpak"]: results += search_flatpak(args.package)
        if args.source in ["auto", "all", "snap"]: results += search_snap(args.package)

        if args.format == "json":
            print(json.dumps(results, indent=2))
        else:
            print(f"\n📋 {len(results)} résultats:")
            for r in results[:15]:
                print(f"  [{r['source']:7}] {r['name']}: {r['desc'][:50]}")

    elif args.command == "install" and args.package:
        print(f"📥 Installation de {args.package}...")
        ok, out = install(args.package, args.source)
        if ok: print(f"✅ Installé: {args.package}")
        else: print(f"❌ Échec: {out[:100]}")

    elif args.command == "remove" and args.package:
        print(f"🗑️ Suppression de {args.package}...")
        ok, out = remove(args.package, args.source)
        if ok: print(f"✅ Supprimé: {args.package}")
        else: print(f"❌ Échec: {out[:100]}")

    elif args.command == "list":
        installed = list_installed(args.source)
        if args.format == "json":
            print(json.dumps(installed, indent=2))
        else:
            print(f"\n📦 {len(installed)} paquets installés")
            by_source = {}
            for p in installed:
                by_source.setdefault(p["source"], []).append(p["name"])
            for src, pkgs in by_source.items():
                print(f"  {src}: {len(pkgs)} paquets")

    elif args.command == "update":
        print("🔄 Mise à jour de tous les gestionnaires...")
        results = update_all()
        for src, ok in results:
            status = "✅" if ok else "❌"
            print(f"  {status} {src}")

if __name__ == "__main__":
    main()
