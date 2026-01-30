#!/usr/bin/env python3
"""
AURA-OS Agent: System Cleaner
Team: PC-Admin
Description: Scanne et nettoie les fichiers obsolètes, liens cassés, caches gonflés
"""

import subprocess
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import shutil
import json

LOGGER_PATH = Path.home() / ".aura" / "agents" / "logger_master.py"

def log_action(status: str, message: str, details: str = None):
    """Log une action via logger_master"""
    cmd = [
        "python3", str(LOGGER_PATH),
        "--team", "pc-admin",
        "--agent", "system_cleaner",
        "--status", status,
        "--message", message
    ]
    if details:
        cmd.extend(["--details", details])
    subprocess.run(cmd, capture_output=True)

def format_size(size_bytes):
    """Formate une taille en bytes vers humain lisible"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

def get_dir_size(path):
    """Calcule la taille d'un répertoire"""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False):
                total += get_dir_size(entry.path)
    except (PermissionError, OSError):
        pass
    return total

def scan_broken_symlinks(paths=None):
    """Trouve les liens symboliques cassés"""
    if paths is None:
        paths = [
            Path.home(),
            Path("/usr/local/bin"),
        ]

    broken = []
    for base_path in paths:
        if not base_path.exists():
            continue

        try:
            result = subprocess.run(
                ["find", str(base_path), "-maxdepth", "4", "-xtype", "l", "-print"],
                capture_output=True, text=True, timeout=60
            )
            for line in result.stdout.strip().split('\n'):
                if line:
                    broken.append(line)
        except (subprocess.TimeoutExpired, Exception):
            pass

    return broken

def scan_old_logs(days=30, min_size_mb=1):
    """Trouve les vieux fichiers logs"""
    log_dirs = [
        Path.home() / ".local/share",
        Path.home() / ".cache",
        Path("/var/log") if os.access("/var/log", os.R_OK) else None,
    ]

    old_logs = []
    cutoff = datetime.now() - timedelta(days=days)

    for log_dir in log_dirs:
        if log_dir is None or not log_dir.exists():
            continue

        try:
            for log_file in log_dir.rglob("*.log"):
                try:
                    stat = log_file.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    size_mb = stat.st_size / (1024 * 1024)

                    if mtime < cutoff and size_mb >= min_size_mb:
                        old_logs.append({
                            'path': str(log_file),
                            'size': stat.st_size,
                            'size_human': format_size(stat.st_size),
                            'modified': mtime.strftime('%Y-%m-%d'),
                            'age_days': (datetime.now() - mtime).days
                        })
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass

    return sorted(old_logs, key=lambda x: x['size'], reverse=True)

def scan_cache_dirs():
    """Analyse les répertoires de cache"""
    cache_dirs = [
        (Path.home() / ".cache", "Cache utilisateur"),
        (Path.home() / ".local/share/Trash", "Corbeille"),
        (Path("/tmp"), "Fichiers temporaires"),
        (Path.home() / ".thumbnails", "Thumbnails"),
        (Path.home() / ".local/share/thumbnails", "Thumbnails KDE"),
        (Path.home() / ".mozilla/firefox", "Cache Firefox (profils)"),
        (Path.home() / "snap", "Données Snap"),
        (Path.home() / ".npm/_cacache", "Cache NPM"),
        (Path.home() / ".cache/pip", "Cache Pip"),
        (Path.home() / ".cache/yarn", "Cache Yarn"),
        (Path.home() / ".gradle/caches", "Cache Gradle"),
    ]

    results = []
    for cache_path, name in cache_dirs:
        if cache_path.exists():
            size = get_dir_size(cache_path)
            if size > 1024 * 1024:  # > 1MB
                results.append({
                    'name': name,
                    'path': str(cache_path),
                    'size': size,
                    'size_human': format_size(size)
                })

    return sorted(results, key=lambda x: x['size'], reverse=True)

def scan_orphan_packages():
    """Trouve les paquets orphelins (apt)"""
    orphans = []

    try:
        # Paquets auto-installés qui ne sont plus nécessaires
        result = subprocess.run(
            ["apt", "list", "--installed"],
            capture_output=True, text=True, timeout=30
        )

        # Utiliser deborphan si disponible
        orphan_result = subprocess.run(
            ["deborphan"],
            capture_output=True, text=True, timeout=30
        )
        if orphan_result.returncode == 0:
            orphans = [p for p in orphan_result.stdout.strip().split('\n') if p]

    except (subprocess.TimeoutExpired, FileNotFoundError):
        # deborphan pas installé, utiliser apt autoremove --dry-run
        try:
            result = subprocess.run(
                ["apt", "autoremove", "--dry-run"],
                capture_output=True, text=True, timeout=30
            )
            for line in result.stdout.split('\n'):
                if line.strip().startswith('Remv '):
                    pkg = line.split()[1]
                    orphans.append(pkg)
        except:
            pass

    return orphans

def scan_coredumps():
    """Trouve les core dumps"""
    coredumps = []

    # Chercher dans les emplacements communs
    patterns = [
        Path.home() / "core*",
        Path("/var/crash"),
        Path.home() / ".local/share/systemd/coredump",
    ]

    for pattern in patterns:
        if '*' in str(pattern):
            base = pattern.parent
            glob_pattern = pattern.name
            if base.exists():
                for f in base.glob(glob_pattern):
                    if f.is_file():
                        coredumps.append({
                            'path': str(f),
                            'size': f.stat().st_size,
                            'size_human': format_size(f.stat().st_size)
                        })
        elif pattern.exists():
            if pattern.is_dir():
                for f in pattern.iterdir():
                    if f.is_file():
                        coredumps.append({
                            'path': str(f),
                            'size': f.stat().st_size,
                            'size_human': format_size(f.stat().st_size)
                        })

    return coredumps

def scan_duplicate_downloads():
    """Trouve les fichiers potentiellement dupliqués dans Downloads"""
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        return []

    # Chercher les fichiers avec (1), (2), copy, etc.
    duplicates = []
    patterns = ["*(*)*", "*copy*", "*copie*", "* - Copy*"]

    for pattern in patterns:
        for f in downloads.glob(pattern):
            if f.is_file():
                duplicates.append({
                    'path': str(f),
                    'size': f.stat().st_size,
                    'size_human': format_size(f.stat().st_size)
                })

    return duplicates

def full_scan(format_output="text"):
    """Effectue un scan complet du système"""
    results = {
        'timestamp': datetime.now().isoformat(),
        'broken_symlinks': scan_broken_symlinks(),
        'old_logs': scan_old_logs(),
        'cache_dirs': scan_cache_dirs(),
        'orphan_packages': scan_orphan_packages(),
        'coredumps': scan_coredumps(),
        'duplicate_downloads': scan_duplicate_downloads()
    }

    # Calculer les totaux
    total_cache = sum(c['size'] for c in results['cache_dirs'])
    total_logs = sum(l['size'] for l in results['old_logs'])

    results['summary'] = {
        'broken_symlinks_count': len(results['broken_symlinks']),
        'old_logs_count': len(results['old_logs']),
        'old_logs_size': format_size(total_logs),
        'cache_size': format_size(total_cache),
        'orphan_packages_count': len(results['orphan_packages']),
        'coredumps_count': len(results['coredumps']),
        'duplicate_downloads_count': len(results['duplicate_downloads'])
    }

    if format_output == "json":
        return json.dumps(results, indent=2, default=str)

    # Format texte
    output = []
    output.append("=" * 60)
    output.append("  AURA-OS SYSTEM CLEANER - RAPPORT DE SCAN")
    output.append("=" * 60)
    output.append(f"  Date: {results['timestamp'][:19]}")
    output.append("")

    # Résumé
    output.append("📊 RÉSUMÉ")
    output.append("-" * 40)
    s = results['summary']
    output.append(f"  • Liens cassés:        {s['broken_symlinks_count']}")
    output.append(f"  • Vieux logs (>30j):   {s['old_logs_count']} ({s['old_logs_size']})")
    output.append(f"  • Taille des caches:   {s['cache_size']}")
    output.append(f"  • Paquets orphelins:   {s['orphan_packages_count']}")
    output.append(f"  • Core dumps:          {s['coredumps_count']}")
    output.append(f"  • Downloads dupliqués: {s['duplicate_downloads_count']}")
    output.append("")

    # Détails des caches
    output.append("💾 CACHES (Top 10)")
    output.append("-" * 40)
    for c in results['cache_dirs'][:10]:
        output.append(f"  {c['size_human']:>10}  {c['name']}")
    output.append("")

    # Liens cassés
    if results['broken_symlinks']:
        output.append(f"🔗 LIENS CASSÉS ({len(results['broken_symlinks'])})")
        output.append("-" * 40)
        for link in results['broken_symlinks'][:10]:
            output.append(f"  {link}")
        if len(results['broken_symlinks']) > 10:
            output.append(f"  ... et {len(results['broken_symlinks']) - 10} autres")
        output.append("")

    # Vieux logs
    if results['old_logs']:
        output.append(f"📜 VIEUX LOGS (Top 5)")
        output.append("-" * 40)
        for log in results['old_logs'][:5]:
            output.append(f"  {log['size_human']:>10}  {log['age_days']}j  {log['path']}")
        output.append("")

    # Paquets orphelins
    if results['orphan_packages']:
        output.append(f"📦 PAQUETS ORPHELINS")
        output.append("-" * 40)
        output.append(f"  {', '.join(results['orphan_packages'][:10])}")
        output.append("  → sudo apt autoremove pour nettoyer")
        output.append("")

    return '\n'.join(output)

def clean_cache(target, dry_run=False):
    """Nettoie un cache spécifique"""
    targets = {
        'trash': Path.home() / ".local/share/Trash",
        'thumbnails': [
            Path.home() / ".thumbnails",
            Path.home() / ".local/share/thumbnails"
        ],
        'tmp': Path("/tmp"),
        'pip': Path.home() / ".cache/pip",
        'npm': Path.home() / ".npm/_cacache",
        'yarn': Path.home() / ".cache/yarn",
    }

    if target not in targets:
        return f"Cible inconnue: {target}. Disponibles: {', '.join(targets.keys())}"

    paths = targets[target]
    if not isinstance(paths, list):
        paths = [paths]

    total_freed = 0
    for path in paths:
        if not path.exists():
            continue

        size = get_dir_size(path)
        total_freed += size

        if dry_run:
            print(f"[DRY-RUN] Supprimerait: {path} ({format_size(size)})")
        else:
            try:
                if target == 'tmp':
                    # Pour /tmp, supprimer seulement les fichiers de l'utilisateur
                    for item in path.iterdir():
                        try:
                            if item.owner() == os.getlogin():
                                if item.is_dir():
                                    shutil.rmtree(item)
                                else:
                                    item.unlink()
                        except:
                            pass
                else:
                    shutil.rmtree(path)
                    path.mkdir(parents=True, exist_ok=True)
                print(f"✅ Nettoyé: {path} ({format_size(size)})")
            except Exception as e:
                print(f"❌ Erreur: {path} - {e}")

    if not dry_run:
        log_action('success', f"Cache {target} nettoyé", f"{format_size(total_freed)} libérés")

    return f"Total libéré: {format_size(total_freed)}"

def remove_broken_links(dry_run=False):
    """Supprime les liens symboliques cassés"""
    broken = scan_broken_symlinks()

    if not broken:
        return "Aucun lien cassé trouvé."

    removed = 0
    for link in broken:
        path = Path(link)
        if dry_run:
            print(f"[DRY-RUN] Supprimerait: {link}")
            removed += 1
        else:
            try:
                path.unlink()
                print(f"✅ Supprimé: {link}")
                removed += 1
            except Exception as e:
                print(f"❌ Erreur: {link} - {e}")

    if not dry_run:
        log_action('success', f"{removed} liens cassés supprimés")

    return f"{removed} lien(s) traité(s)"

def main():
    parser = argparse.ArgumentParser(
        description="AURA-OS System Cleaner - Nettoie les fichiers obsolètes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s scan                    Scan complet du système
  %(prog)s scan --format json      Sortie JSON
  %(prog)s clean trash             Vide la corbeille
  %(prog)s clean thumbnails        Nettoie les thumbnails
  %(prog)s clean pip               Nettoie le cache pip
  %(prog)s fix-links               Supprime les liens cassés
  %(prog)s fix-links --dry-run     Simule la suppression

Cibles de nettoyage: trash, thumbnails, tmp, pip, npm, yarn
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commande")

    # Scan
    scan_parser = subparsers.add_parser("scan", help="Scanne le système")
    scan_parser.add_argument("--format", choices=["text", "json"], default="text")

    # Clean
    clean_parser = subparsers.add_parser("clean", help="Nettoie un cache")
    clean_parser.add_argument("target", choices=["trash", "thumbnails", "tmp", "pip", "npm", "yarn"])
    clean_parser.add_argument("--dry-run", "-n", action="store_true")

    # Fix links
    links_parser = subparsers.add_parser("fix-links", help="Supprime les liens cassés")
    links_parser.add_argument("--dry-run", "-n", action="store_true")

    args = parser.parse_args()

    if args.command == "scan":
        print(full_scan(args.format))

    elif args.command == "clean":
        print(clean_cache(args.target, args.dry_run))

    elif args.command == "fix-links":
        print(remove_broken_links(args.dry_run))

    else:
        # Par défaut, scan
        print(full_scan())

if __name__ == "__main__":
    main()
