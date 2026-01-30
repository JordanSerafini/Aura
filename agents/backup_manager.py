#!/usr/bin/env python3
"""
AURA-OS Backup Manager Agent
Sauvegardes automatisées intelligentes
Team: pc-admin
"""

import argparse
import json
import os
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path
import hashlib

BACKUP_DIR = Path.home() / "Backups" / "aura"
CONFIG_FILE = Path.home() / ".aura" / "backup_config.json"
HISTORY_FILE = Path.home() / ".aura" / "backup_history.json"

# Configuration par défaut
DEFAULT_CONFIG = {
    "version": "1.0.0",
    "profiles": {
        "aura": {
            "name": "Aura System",
            "paths": ["~/.aura"],
            "exclude": ["*.pyc", "__pycache__", "*.log", "chroma_db", "venv"],
            "compression": "gz",
            "keep_last": 5
        },
        "claude": {
            "name": "Claude Config",
            "paths": ["~/.claude"],
            "exclude": ["cache", "*.log", "telemetry", "statsig", "file-history"],
            "compression": "gz",
            "keep_last": 3
        },
        "dotfiles": {
            "name": "Dotfiles",
            "paths": [
                "~/.bashrc", "~/.zshrc", "~/.gitconfig",
                "~/.config/Code/User/settings.json",
                "~/.config/Code/User/keybindings.json"
            ],
            "exclude": [],
            "compression": "gz",
            "keep_last": 10
        },
        "projects": {
            "name": "Projects",
            "paths": ["~/Projects"],
            "exclude": ["node_modules", "venv", ".venv", "target", "dist", "__pycache__", ".git"],
            "compression": "gz",
            "keep_last": 3
        }
    },
    "auto_backup": {
        "enabled": False,
        "profiles": ["aura", "claude"],
        "interval": "1d"
    }
}

def load_config() -> dict:
    """Charge la configuration"""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return DEFAULT_CONFIG.copy()

def save_config(config: dict):
    """Sauvegarde la configuration"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))

def load_history() -> list:
    """Charge l'historique des backups"""
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []

def save_history(history: list):
    """Sauvegarde l'historique"""
    HISTORY_FILE.write_text(json.dumps(history[-100:], indent=2, ensure_ascii=False))

def expand_path(path: str) -> Path:
    """Expand ~ et variables d'environnement"""
    return Path(os.path.expanduser(os.path.expandvars(path)))

def get_size_str(size_bytes: int) -> str:
    """Convertit bytes en string lisible"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def calculate_checksum(file_path: Path) -> str:
    """Calcule le checksum MD5 d'un fichier"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def create_backup(profile_name: str, config: dict, dry_run: bool = False) -> dict | None:
    """Crée une sauvegarde pour un profil"""
    if profile_name not in config["profiles"]:
        print(f"[-] Profil inconnu: {profile_name}")
        return None

    profile = config["profiles"][profile_name]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{profile_name}_{timestamp}.tar.gz"
    backup_path = BACKUP_DIR / profile_name / backup_name

    print(f"[*] Création backup: {profile['name']}")

    # Prépare les chemins
    paths_to_backup = []
    total_size = 0

    for path_str in profile["paths"]:
        path = expand_path(path_str)
        if path.exists():
            paths_to_backup.append(path)
            if path.is_file():
                total_size += path.stat().st_size
            else:
                for f in path.rglob("*"):
                    if f.is_file():
                        # Check excludes
                        skip = False
                        for excl in profile.get("exclude", []):
                            if f.match(excl) or any(excl in str(f) for excl in profile.get("exclude", [])):
                                skip = True
                                break
                        if not skip:
                            total_size += f.stat().st_size
        else:
            print(f"  [!] Chemin non trouvé: {path}")

    if not paths_to_backup:
        print("[-] Aucun chemin valide à sauvegarder")
        return None

    print(f"  Chemins: {len(paths_to_backup)}")
    print(f"  Taille estimée: {get_size_str(total_size)}")

    if dry_run:
        print("  [DRY-RUN] Backup non créé")
        return {"status": "dry_run", "estimated_size": total_size}

    # Crée le répertoire de backup
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # Crée l'archive
    start_time = datetime.now()

    try:
        with tarfile.open(backup_path, "w:gz") as tar:
            for path in paths_to_backup:
                # Filtre les exclusions
                def filter_func(tarinfo):
                    for excl in profile.get("exclude", []):
                        if excl in tarinfo.name or tarinfo.name.endswith(excl.replace("*", "")):
                            return None
                    return tarinfo

                tar.add(path, arcname=path.name, filter=filter_func)

        duration = (datetime.now() - start_time).total_seconds()
        final_size = backup_path.stat().st_size
        checksum = calculate_checksum(backup_path)

        result = {
            "profile": profile_name,
            "name": backup_name,
            "path": str(backup_path),
            "size": final_size,
            "size_str": get_size_str(final_size),
            "checksum": checksum,
            "created_at": datetime.now().isoformat(),
            "duration": round(duration, 2),
            "status": "success"
        }

        print(f"  [+] Créé: {backup_name}")
        print(f"  Taille: {result['size_str']} | Durée: {duration:.1f}s")

        # Enregistre dans l'historique
        history = load_history()
        history.append(result)
        save_history(history)

        # Nettoyage des anciens backups
        cleanup_old_backups(profile_name, profile.get("keep_last", 5))

        return result

    except Exception as e:
        print(f"  [-] Erreur: {e}")
        return {"status": "error", "error": str(e)}

def cleanup_old_backups(profile_name: str, keep_last: int):
    """Supprime les anciens backups au-delà de keep_last"""
    profile_dir = BACKUP_DIR / profile_name
    if not profile_dir.exists():
        return

    backups = sorted(profile_dir.glob("*.tar.gz"), key=lambda x: x.stat().st_mtime, reverse=True)

    if len(backups) > keep_last:
        for old_backup in backups[keep_last:]:
            old_backup.unlink()
            print(f"  [i] Supprimé ancien: {old_backup.name}")

def restore_backup(backup_path: str, destination: str | None = None, dry_run: bool = False) -> bool:
    """Restaure une sauvegarde"""
    backup = Path(backup_path)
    if not backup.exists():
        # Cherche dans BACKUP_DIR
        for profile_dir in BACKUP_DIR.iterdir():
            candidate = profile_dir / backup_path
            if candidate.exists():
                backup = candidate
                break

    if not backup.exists():
        print(f"[-] Backup non trouvé: {backup_path}")
        return False

    dest = Path(destination) if destination else Path.home()

    print(f"[*] Restauration de {backup.name}")
    print(f"  Destination: {dest}")

    if dry_run:
        with tarfile.open(backup, "r:gz") as tar:
            print(f"  Contenu:")
            for member in tar.getmembers()[:20]:
                print(f"    {member.name}")
            if len(tar.getmembers()) > 20:
                print(f"    ... et {len(tar.getmembers()) - 20} autres fichiers")
        print("  [DRY-RUN] Non restauré")
        return True

    try:
        with tarfile.open(backup, "r:gz") as tar:
            tar.extractall(dest)
        print(f"  [+] Restauré avec succès")
        return True
    except Exception as e:
        print(f"  [-] Erreur: {e}")
        return False

def list_backups(profile_name: str | None = None):
    """Liste les backups disponibles"""
    if not BACKUP_DIR.exists():
        print("[i] Aucun backup trouvé")
        return

    print(f"\n{'='*70}")
    print(f"{'Profil':<15} {'Nom':<35} {'Taille':<10} {'Date':<10}")
    print(f"{'='*70}")

    total_size = 0
    count = 0

    for profile_dir in sorted(BACKUP_DIR.iterdir()):
        if profile_name and profile_dir.name != profile_name:
            continue

        if profile_dir.is_dir():
            for backup in sorted(profile_dir.glob("*.tar.gz"), reverse=True):
                size = backup.stat().st_size
                total_size += size
                count += 1
                date = datetime.fromtimestamp(backup.stat().st_mtime).strftime("%Y-%m-%d")
                print(f"{profile_dir.name:<15} {backup.name:<35} {get_size_str(size):<10} {date}")

    print(f"{'='*70}")
    print(f"Total: {count} backups, {get_size_str(total_size)}\n")

def run_all_profiles(config: dict, profiles: list | None = None, dry_run: bool = False):
    """Exécute les backups pour tous les profils (ou une liste spécifique)"""
    profiles_to_run = profiles or list(config["profiles"].keys())

    print(f"[*] Backup de {len(profiles_to_run)} profil(s)...\n")

    results = []
    for profile in profiles_to_run:
        result = create_backup(profile, config, dry_run)
        if result:
            results.append(result)
        print()

    # Résumé
    success = sum(1 for r in results if r.get("status") == "success")
    print(f"[{'+'if success == len(results) else '!'}] Terminé: {success}/{len(results)} backups réussis")

    return results

def main():
    parser = argparse.ArgumentParser(
        description="AURA Backup Manager - Sauvegardes automatisées intelligentes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s run aura                  # Backup du profil 'aura'
  %(prog)s run --all                 # Backup de tous les profils
  %(prog)s list                      # Liste les backups
  %(prog)s restore aura_20260130.tar.gz
  %(prog)s profiles                  # Liste les profils configurés
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commandes")

    # run
    run_parser = subparsers.add_parser("run", help="Créer un backup")
    run_parser.add_argument("profile", nargs="?", help="Profil à sauvegarder")
    run_parser.add_argument("--all", "-a", action="store_true", help="Tous les profils")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulation")

    # restore
    restore_parser = subparsers.add_parser("restore", help="Restaurer un backup")
    restore_parser.add_argument("backup", help="Nom ou chemin du backup")
    restore_parser.add_argument("--dest", "-d", help="Destination")
    restore_parser.add_argument("--dry-run", action="store_true", help="Simulation")

    # list
    list_parser = subparsers.add_parser("list", help="Lister les backups")
    list_parser.add_argument("profile", nargs="?", help="Filtrer par profil")

    # profiles
    subparsers.add_parser("profiles", help="Lister les profils configurés")

    # history
    hist_parser = subparsers.add_parser("history", help="Historique des backups")
    hist_parser.add_argument("--limit", "-n", type=int, default=10)

    # init
    subparsers.add_parser("init", help="Initialiser la configuration")

    args = parser.parse_args()
    config = load_config()

    if args.command == "run":
        if args.all:
            run_all_profiles(config, dry_run=args.dry_run)
        elif args.profile:
            create_backup(args.profile, config, args.dry_run)
        else:
            print("[-] Spécifiez un profil ou utilisez --all")

    elif args.command == "restore":
        restore_backup(args.backup, args.dest, args.dry_run)

    elif args.command == "list":
        list_backups(args.profile)

    elif args.command == "profiles":
        print(f"\n Profils configurés:")
        for name, profile in config["profiles"].items():
            paths_count = len(profile["paths"])
            print(f"   {name:<15} {profile['name']:<25} ({paths_count} chemins)")
        print()

    elif args.command == "history":
        history = load_history()
        if not history:
            print("[i] Aucun historique")
            return

        print(f"\n{'='*70}")
        print(f"{'Profil':<12} {'Status':<10} {'Taille':<10} {'Durée':<8} {'Date':<20}")
        print(f"{'='*70}")

        for entry in history[-args.limit:]:
            print(f"{entry['profile']:<12} {entry['status']:<10} {entry.get('size_str', 'N/A'):<10} {entry.get('duration', 0):.1f}s     {entry['created_at'][:16]}")

        print(f"{'='*70}\n")

    elif args.command == "init":
        if CONFIG_FILE.exists():
            print("[!] Configuration existe déjà")
            return
        save_config(DEFAULT_CONFIG)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[+] Configuration créée: {CONFIG_FILE}")
        print(f"[+] Répertoire backup: {BACKUP_DIR}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
