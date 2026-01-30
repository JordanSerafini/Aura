#!/usr/bin/env python3
"""
AURA-OS Agent: Claude Cleaner
Team: PC-Admin
Description: Nettoie les instances orphelines de Claude Code pour éviter les freezes système
"""

import subprocess
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

LOGGER_PATH = Path.home() / ".aura" / "agents" / "logger_master.py"

def log_action(status: str, message: str, details: str = None):
    """Log une action via logger_master"""
    cmd = [
        "python3", str(LOGGER_PATH),
        "--team", "pc-admin",
        "--agent", "claude_cleaner",
        "--status", status,
        "--message", message
    ]
    if details:
        cmd.extend(["--details", details])
    subprocess.run(cmd, capture_output=True)

def get_claude_processes():
    """Récupère toutes les instances Claude en cours"""
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True, text=True
    )

    processes = []
    for line in result.stdout.strip().split('\n')[1:]:
        parts = line.split(None, 10)
        if len(parts) >= 11 and 'claude' in parts[10].lower():
            # Exclure les grep et les processus shell
            if 'grep' in parts[10] or '/bin/zsh' in parts[10]:
                continue

            pid = int(parts[1])
            cpu = float(parts[2])
            mem = float(parts[3])
            rss_kb = int(parts[5])
            start = parts[8]
            command = parts[10]

            # Vérifier si c'est un processus détaché (tty = ?)
            tty = parts[6]
            is_orphan = tty == '?'

            processes.append({
                'pid': pid,
                'cpu': cpu,
                'mem': mem,
                'rss_mb': rss_kb // 1024,
                'start': start,
                'tty': tty,
                'is_orphan': is_orphan,
                'command': command[:50]
            })

    return processes

def get_current_claude_pid():
    """Trouve le PID de l'instance Claude actuelle (celle qui exécute ce script)"""
    # Remonter l'arbre des processus pour trouver claude
    current_pid = os.getpid()

    while current_pid > 1:
        try:
            stat_path = Path(f"/proc/{current_pid}/stat")
            if stat_path.exists():
                stat = stat_path.read_text().split()
                ppid = int(stat[3])
                comm = stat[1].strip('()')

                if 'claude' in comm.lower():
                    return current_pid

                current_pid = ppid
            else:
                break
        except:
            break

    return None

def clean_orphans(dry_run=False, force=False):
    """Nettoie les instances Claude orphelines"""
    processes = get_claude_processes()
    current_pid = get_current_claude_pid()

    orphans = [p for p in processes if p['is_orphan'] and p['pid'] != current_pid]

    if not orphans:
        return {
            'status': 'clean',
            'message': 'Aucune instance orpheline trouvée',
            'killed': []
        }

    result = {
        'status': 'cleaned',
        'message': f'{len(orphans)} instance(s) orpheline(s) trouvée(s)',
        'killed': []
    }

    total_ram_freed = 0

    for proc in orphans:
        if dry_run:
            result['killed'].append({
                'pid': proc['pid'],
                'ram_mb': proc['rss_mb'],
                'action': 'would_kill'
            })
        else:
            signal = '-9' if force else '-15'
            kill_result = subprocess.run(
                ['kill', signal, str(proc['pid'])],
                capture_output=True
            )

            if kill_result.returncode == 0:
                total_ram_freed += proc['rss_mb']
                result['killed'].append({
                    'pid': proc['pid'],
                    'ram_mb': proc['rss_mb'],
                    'action': 'killed'
                })
            else:
                result['killed'].append({
                    'pid': proc['pid'],
                    'ram_mb': proc['rss_mb'],
                    'action': 'failed'
                })

    result['ram_freed_mb'] = total_ram_freed

    # Logger l'action
    if not dry_run and result['killed']:
        log_action(
            'success',
            f"Nettoyage: {len(result['killed'])} instances, {total_ram_freed} MB libérés",
            f"PIDs: {[k['pid'] for k in result['killed']]}"
        )

    return result

def status():
    """Affiche le statut des instances Claude"""
    processes = get_claude_processes()
    current_pid = get_current_claude_pid()

    if not processes:
        print("Aucune instance Claude en cours.")
        return

    print(f"{'PID':>7} {'CPU%':>6} {'RAM':>8} {'TTY':>8} {'ORPHAN':>8} {'COMMAND':<40}")
    print("-" * 85)

    total_ram = 0
    orphan_count = 0

    for p in processes:
        is_current = " (ACTUEL)" if p['pid'] == current_pid else ""
        orphan_mark = "OUI" if p['is_orphan'] else "non"

        if p['is_orphan'] and p['pid'] != current_pid:
            orphan_count += 1

        total_ram += p['rss_mb']

        print(f"{p['pid']:>7} {p['cpu']:>6.1f} {p['rss_mb']:>6} MB {p['tty']:>8} {orphan_mark:>8} {p['command']:<30}{is_current}")

    print("-" * 85)
    print(f"Total: {len(processes)} instance(s), {total_ram} MB RAM, {orphan_count} orpheline(s)")

    if orphan_count > 0:
        print(f"\n ATTENTION: {orphan_count} instance(s) orpheline(s) détectée(s)!")
        print("   Utilisez 'python3 claude_cleaner.py clean' pour les nettoyer.")

def main():
    parser = argparse.ArgumentParser(
        description="AURA-OS Claude Cleaner - Nettoie les instances Claude orphelines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s status              Affiche l'état des instances Claude
  %(prog)s clean               Nettoie les instances orphelines (SIGTERM)
  %(prog)s clean --force       Force le nettoyage (SIGKILL)
  %(prog)s clean --dry-run     Simule le nettoyage sans tuer

Ce problème survient quand Claude Code est fermé de manière non propre
(Ctrl+C, fermeture du terminal, etc.). Les processus restent en arrière-plan
et accumulent de la mémoire, causant des freezes système.
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commande")

    # Status
    subparsers.add_parser("status", help="Affiche l'état des instances Claude")

    # Clean
    clean_parser = subparsers.add_parser("clean", help="Nettoie les instances orphelines")
    clean_parser.add_argument("--force", "-f", action="store_true", help="Utilise SIGKILL au lieu de SIGTERM")
    clean_parser.add_argument("--dry-run", "-n", action="store_true", help="Simule sans tuer")
    clean_parser.add_argument("--quiet", "-q", action="store_true", help="Mode silencieux")

    args = parser.parse_args()

    if args.command == "status":
        status()

    elif args.command == "clean":
        result = clean_orphans(dry_run=args.dry_run, force=args.force)

        if not args.quiet:
            print(f"Statut: {result['status']}")
            print(f"Message: {result['message']}")

            if result['killed']:
                print(f"\nProcessus traités:")
                for k in result['killed']:
                    print(f"  PID {k['pid']}: {k['action']} ({k['ram_mb']} MB)")

                if 'ram_freed_mb' in result:
                    print(f"\nRAM libérée: {result['ram_freed_mb']} MB")

    else:
        # Par défaut, afficher le status
        status()

if __name__ == "__main__":
    main()
