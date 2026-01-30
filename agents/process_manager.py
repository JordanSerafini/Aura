#!/usr/bin/env python3
"""
AURA-OS Agent: Process Manager
Team: PC-Admin
Description: Gestion des processus - liste, monitoring CPU/GPU, lancement, fermeture
"""

import subprocess
import argparse
import json
import os
import sys
from pathlib import Path

# Chemin vers le logger
LOGGER_PATH = Path.home() / ".aura" / "agents" / "logger_master.py"

def log_action(status: str, message: str, details: str = None):
    """Log une action via logger_master"""
    cmd = [
        "python3", str(LOGGER_PATH),
        "--team", "pc-admin",
        "--agent", "process_manager",
        "--status", status,
        "--message", message
    ]
    if details:
        cmd.extend(["--details", details])
    subprocess.run(cmd, capture_output=True)

def get_gpu_processes():
    """Récupère les processus utilisant le GPU (NVIDIA)"""
    gpu_procs = {}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory,name", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 2:
                        pid = parts[0]
                        mem = parts[1] if len(parts) > 1 else "0"
                        name = parts[2] if len(parts) > 2 else "N/A"
                        gpu_procs[pid] = {"gpu_mem_mb": mem, "gpu_name": name}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return gpu_procs

def get_gpu_usage():
    """Récupère l'utilisation globale du GPU"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(',')]
            return {
                "gpu_util": f"{parts[0]}%",
                "gpu_mem_used": f"{parts[1]} MB",
                "gpu_mem_total": f"{parts[2]} MB",
                "gpu_temp": f"{parts[3]}°C"
            }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None

def list_processes(sort_by="cpu", limit=20, filter_name=None, format_output="text"):
    """Liste les processus avec leur utilisation CPU/RAM/GPU"""
    gpu_procs = get_gpu_processes()

    # Utiliser ps pour obtenir les processus
    ps_cmd = ["ps", "aux", "--sort", f"-{sort_by}"]
    result = subprocess.run(ps_cmd, capture_output=True, text=True)

    lines = result.stdout.strip().split('\n')
    header = lines[0]
    processes = []

    for line in lines[1:limit+1]:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            pid = parts[1]
            proc = {
                "user": parts[0],
                "pid": pid,
                "cpu": parts[2],
                "mem": parts[3],
                "vsz": parts[4],
                "rss": parts[5],
                "tty": parts[6],
                "stat": parts[7],
                "start": parts[8],
                "time": parts[9],
                "command": parts[10][:60]
            }

            # Ajouter info GPU si disponible
            if pid in gpu_procs:
                proc["gpu_mem"] = gpu_procs[pid]["gpu_mem_mb"] + " MB"

            # Filtrer si demandé
            if filter_name:
                if filter_name.lower() not in proc["command"].lower():
                    continue

            processes.append(proc)

    if format_output == "json":
        return json.dumps(processes, indent=2)
    else:
        # Format texte tableau
        output = []
        output.append(f"{'PID':>7} {'CPU%':>6} {'MEM%':>6} {'GPU':>8} {'COMMAND':<50}")
        output.append("-" * 80)
        for p in processes:
            gpu = p.get("gpu_mem", "-")
            cmd = p["command"][:48]
            output.append(f"{p['pid']:>7} {p['cpu']:>6} {p['mem']:>6} {gpu:>8} {cmd:<50}")
        return '\n'.join(output)

def top_processes(count=10, format_output="text"):
    """Affiche les processus les plus gourmands en CPU et RAM"""
    gpu_info = get_gpu_usage()

    output = []
    output.append("=" * 60)
    output.append("  TOP PROCESSUS - AURA-OS PROCESS MANAGER")
    output.append("=" * 60)

    if gpu_info:
        output.append(f"\n GPU: {gpu_info['gpu_util']} | VRAM: {gpu_info['gpu_mem_used']}/{gpu_info['gpu_mem_total']} | Temp: {gpu_info['gpu_temp']}")

    output.append("\n TOP CPU:")
    output.append("-" * 40)
    output.append(list_processes(sort_by="cpu", limit=count))

    output.append("\n TOP MÉMOIRE:")
    output.append("-" * 40)
    output.append(list_processes(sort_by="rss", limit=count))

    return '\n'.join(output)

def kill_process(identifier, force=False):
    """Tue un processus par PID ou nom"""
    signal = "-9" if force else "-15"

    # Vérifier si c'est un PID ou un nom
    if identifier.isdigit():
        cmd = ["kill", signal, identifier]
        target = f"PID {identifier}"
    else:
        cmd = ["pkill", signal.replace("-", "-"), identifier]
        target = f"processus '{identifier}'"

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        log_action("success", f"Processus terminé: {target}")
        return f"Processus {target} terminé avec succès"
    else:
        log_action("error", f"Échec fermeture: {target}", result.stderr)
        return f"Erreur: impossible de terminer {target}\n{result.stderr}"

def launch_app(app_name, args=None, detach=True):
    """Lance une application"""
    cmd = [app_name]
    if args:
        cmd.extend(args.split())

    try:
        if detach:
            # Lancer en arrière-plan, détaché du terminal
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            log_action("success", f"Application lancée: {app_name}", f"PID: {process.pid}")
            return f"Application '{app_name}' lancée (PID: {process.pid})"
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.stdout
    except FileNotFoundError:
        log_action("error", f"Application non trouvée: {app_name}")
        return f"Erreur: application '{app_name}' non trouvée"
    except Exception as e:
        log_action("error", f"Erreur lancement: {app_name}", str(e))
        return f"Erreur: {str(e)}"

def find_app(search_term):
    """Recherche une application dans le système"""
    results = []

    # Chercher dans les .desktop files
    desktop_dirs = [
        Path("/usr/share/applications"),
        Path.home() / ".local/share/applications"
    ]

    for d in desktop_dirs:
        if d.exists():
            for f in d.glob("*.desktop"):
                if search_term.lower() in f.stem.lower():
                    # Lire le fichier pour obtenir le nom et la commande
                    try:
                        content = f.read_text()
                        name = ""
                        exec_cmd = ""
                        for line in content.split('\n'):
                            if line.startswith("Name=") and not name:
                                name = line.split("=", 1)[1]
                            elif line.startswith("Exec="):
                                exec_cmd = line.split("=", 1)[1].split()[0]
                        if name and exec_cmd:
                            results.append({"name": name, "command": exec_cmd, "desktop": f.name})
                    except:
                        pass

    # Chercher aussi avec which
    which_result = subprocess.run(["which", search_term], capture_output=True, text=True)
    if which_result.returncode == 0:
        results.append({"name": search_term, "command": which_result.stdout.strip(), "desktop": None})

    return results

def process_info(pid):
    """Affiche les infos détaillées d'un processus"""
    try:
        # Infos de base
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "pid,ppid,user,%cpu,%mem,vsz,rss,stat,start,time,comm"],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            return f"Processus {pid} non trouvé"

        output = [result.stdout]

        # Ligne de commande complète
        cmdline_path = Path(f"/proc/{pid}/cmdline")
        if cmdline_path.exists():
            cmdline = cmdline_path.read_text().replace('\0', ' ')
            output.append(f"\nCommande: {cmdline}")

        # Fichiers ouverts (limité)
        fd_path = Path(f"/proc/{pid}/fd")
        if fd_path.exists():
            try:
                fds = list(fd_path.iterdir())[:10]
                output.append(f"\nFichiers ouverts: {len(list(fd_path.iterdir()))} (premiers 10):")
                for fd in fds:
                    try:
                        target = fd.resolve()
                        output.append(f"  {fd.name} -> {target}")
                    except:
                        pass
            except PermissionError:
                pass

        # GPU usage si applicable
        gpu_procs = get_gpu_processes()
        if str(pid) in gpu_procs:
            output.append(f"\nGPU: {gpu_procs[str(pid)]['gpu_mem_mb']} MB")

        return '\n'.join(output)

    except Exception as e:
        return f"Erreur: {str(e)}"

def main():
    parser = argparse.ArgumentParser(
        description="AURA-OS Process Manager - Gestion des processus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s list                     Liste les processus (top 20 par CPU)
  %(prog)s list --filter firefox    Filtre par nom
  %(prog)s top                      Affiche les plus gourmands
  %(prog)s kill 12345               Termine le PID 12345
  %(prog)s kill firefox             Termine tous les firefox
  %(prog)s kill firefox --force     Force la fermeture (SIGKILL)
  %(prog)s launch firefox           Lance Firefox
  %(prog)s launch code --args ". "  Lance VS Code avec arguments
  %(prog)s find chrome              Recherche une application
  %(prog)s info 12345               Infos détaillées sur un PID
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commande à exécuter")

    # List
    list_parser = subparsers.add_parser("list", help="Liste les processus")
    list_parser.add_argument("--sort", choices=["cpu", "mem", "rss", "pid"], default="cpu")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.add_argument("--filter", "-f", dest="filter_name", help="Filtrer par nom")
    list_parser.add_argument("--format", choices=["text", "json"], default="text")

    # Top
    top_parser = subparsers.add_parser("top", help="Affiche les processus les plus gourmands")
    top_parser.add_argument("--count", "-n", type=int, default=10)

    # Kill
    kill_parser = subparsers.add_parser("kill", help="Termine un processus")
    kill_parser.add_argument("identifier", help="PID ou nom du processus")
    kill_parser.add_argument("--force", "-f", action="store_true", help="Force (SIGKILL)")

    # Launch
    launch_parser = subparsers.add_parser("launch", help="Lance une application")
    launch_parser.add_argument("app", help="Nom de l'application")
    launch_parser.add_argument("--args", help="Arguments supplémentaires")
    launch_parser.add_argument("--wait", action="store_true", help="Attendre la fin")

    # Find
    find_parser = subparsers.add_parser("find", help="Recherche une application")
    find_parser.add_argument("search", help="Terme de recherche")

    # Info
    info_parser = subparsers.add_parser("info", help="Infos détaillées sur un processus")
    info_parser.add_argument("pid", help="PID du processus")

    args = parser.parse_args()

    if args.command == "list":
        print(list_processes(args.sort, args.limit, args.filter_name, args.format))

    elif args.command == "top":
        print(top_processes(args.count))

    elif args.command == "kill":
        print(kill_process(args.identifier, args.force))

    elif args.command == "launch":
        print(launch_app(args.app, args.args, not args.wait))

    elif args.command == "find":
        results = find_app(args.search)
        if results:
            print(f"Applications trouvées pour '{args.search}':")
            for r in results:
                desktop = f" ({r['desktop']})" if r['desktop'] else ""
                print(f"  {r['name']}: {r['command']}{desktop}")
        else:
            print(f"Aucune application trouvée pour '{args.search}'")

    elif args.command == "info":
        print(process_info(args.pid))

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
