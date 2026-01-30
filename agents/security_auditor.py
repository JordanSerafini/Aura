#!/usr/bin/env python3
"""
AURA-OS Agent: Security Auditor
Team: Cyber
Description: Audit de sécurité système - SSH, ports, firewall, processus suspects
"""

import subprocess
import argparse
import os
import re
import json
from pathlib import Path
from datetime import datetime, timedelta

LOGGER_PATH = Path.home() / ".aura" / "agents" / "logger_master.py"

def log_action(status: str, message: str, details: str = None):
    cmd = [
        "python3", str(LOGGER_PATH),
        "--team", "cyber",
        "--agent", "security_auditor",
        "--status", status,
        "--message", message
    ]
    if details:
        cmd.extend(["--details", details])
    subprocess.run(cmd, capture_output=True)

def run_cmd(cmd, timeout=30):
    """Exécute une commande et retourne le résultat"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "Timeout", -1
    except FileNotFoundError:
        return "Commande non trouvée", -1

def check_ssh_connections():
    """Vérifie les connexions SSH actives"""
    results = {
        'active_sessions': [],
        'listening_ports': [],
        'auth_failures': [],
        'status': 'ok'
    }

    # Sessions SSH actives
    output, _ = run_cmd(["who"])
    for line in output.split('\n'):
        if line:
            results['active_sessions'].append(line)

    # Port SSH en écoute
    output, _ = run_cmd(["ss", "-tlnp"])
    for line in output.split('\n'):
        if ':22 ' in line or 'sshd' in line:
            results['listening_ports'].append(line.strip())

    # Dernières tentatives échouées (auth.log)
    auth_log = Path("/var/log/auth.log")
    if auth_log.exists() and os.access(auth_log, os.R_OK):
        output, _ = run_cmd(["grep", "-i", "failed", str(auth_log)])
        failures = output.split('\n')[-10:]  # 10 dernières
        results['auth_failures'] = [f for f in failures if f]

    if results['auth_failures']:
        results['status'] = 'warning'

    return results

def check_open_ports():
    """Scan des ports ouverts"""
    results = {
        'listening': [],
        'established': [],
        'suspicious': []
    }

    # Ports en écoute
    output, _ = run_cmd(["ss", "-tlnp"])
    for line in output.split('\n')[1:]:
        if line.strip():
            results['listening'].append(line.strip())

    # Connexions établies
    output, _ = run_cmd(["ss", "-tnp"])
    for line in output.split('\n')[1:]:
        if 'ESTAB' in line:
            results['established'].append(line.strip())

    # Ports suspects (haut, non-standard)
    suspicious_ports = [4444, 5555, 6666, 31337, 12345, 54321]
    for line in results['listening']:
        for port in suspicious_ports:
            if f':{port} ' in line:
                results['suspicious'].append(line)

    return results

def check_firewall():
    """Vérifie le statut du firewall"""
    results = {
        'enabled': False,
        'rules': [],
        'status': 'warning'
    }

    # UFW
    output, code = run_cmd(["sudo", "ufw", "status"])
    if code == 0:
        if 'active' in output.lower():
            results['enabled'] = True
            results['status'] = 'ok'
            results['rules'] = output.split('\n')
        else:
            results['status'] = 'critical'
    else:
        # Essayer iptables
        output, code = run_cmd(["sudo", "iptables", "-L", "-n"])
        if code == 0 and 'Chain' in output:
            results['enabled'] = True
            results['rules'] = output.split('\n')[:20]
            results['status'] = 'ok'

    return results

def check_users():
    """Vérifie les utilisateurs et sessions"""
    results = {
        'logged_in': [],
        'sudo_users': [],
        'recent_logins': [],
        'suspicious_users': []
    }

    # Utilisateurs connectés
    output, _ = run_cmd(["who"])
    results['logged_in'] = [l for l in output.split('\n') if l]

    # Utilisateurs sudo
    output, _ = run_cmd(["getent", "group", "sudo"])
    if output:
        users = output.split(':')[-1]
        results['sudo_users'] = users.split(',')

    # Dernières connexions
    output, _ = run_cmd(["last", "-n", "10"])
    results['recent_logins'] = [l for l in output.split('\n') if l and 'wtmp' not in l]

    # Utilisateurs avec UID 0 (root)
    with open('/etc/passwd', 'r') as f:
        for line in f:
            parts = line.split(':')
            if len(parts) > 2 and parts[2] == '0' and parts[0] != 'root':
                results['suspicious_users'].append(parts[0])

    return results

def check_processes():
    """Détecte les processus suspects"""
    results = {
        'high_cpu': [],
        'high_mem': [],
        'suspicious': [],
        'network_active': []
    }

    # Processus avec beaucoup de CPU
    output, _ = run_cmd(["ps", "aux", "--sort=-pcpu"])
    for line in output.split('\n')[1:6]:
        if line:
            results['high_cpu'].append(line)

    # Processus avec réseau actif
    output, _ = run_cmd(["ss", "-tnp"])
    seen_pids = set()
    for line in output.split('\n'):
        match = re.search(r'pid=(\d+)', line)
        if match:
            pid = match.group(1)
            if pid not in seen_pids:
                seen_pids.add(pid)
                # Obtenir le nom du processus
                ps_out, _ = run_cmd(["ps", "-p", pid, "-o", "comm="])
                if ps_out:
                    results['network_active'].append(f"{pid}: {ps_out}")

    # Processus suspects (noms typiques de malware)
    suspicious_names = ['cryptominer', 'xmrig', 'minerd', 'kworker-b', 'kdevtmpfsi']
    output, _ = run_cmd(["ps", "-eo", "pid,comm,args"])
    for line in output.split('\n'):
        parts = line.split()
        if len(parts) >= 2:
            comm = parts[1].lower()
            for name in suspicious_names:
                if name in comm:
                    results['suspicious'].append(line)

    return results

def check_permissions():
    """Vérifie les permissions sensibles"""
    results = {
        'world_writable': [],
        'suid_files': [],
        'ssh_keys': []
    }

    # Fichiers world-writable dans /etc
    output, _ = run_cmd(["find", "/etc", "-maxdepth", "2", "-perm", "-o+w", "-type", "f"], timeout=10)
    results['world_writable'] = [f for f in output.split('\n') if f][:10]

    # Fichiers SUID suspects
    output, _ = run_cmd(["find", "/usr", "-perm", "-4000", "-type", "f"], timeout=30)
    common_suid = ['sudo', 'passwd', 'ping', 'mount', 'umount', 'su', 'chsh', 'gpasswd', 'newgrp', 'pkexec']
    for f in output.split('\n'):
        if f:
            basename = os.path.basename(f)
            if basename not in common_suid:
                results['suid_files'].append(f)

    # Clés SSH
    ssh_dir = Path.home() / ".ssh"
    if ssh_dir.exists():
        for key in ssh_dir.glob("*"):
            if key.is_file():
                stat = key.stat()
                mode = oct(stat.st_mode)[-3:]
                results['ssh_keys'].append({
                    'file': key.name,
                    'permissions': mode,
                    'ok': mode in ['600', '644', '400']
                })

    return results

def check_services():
    """Vérifie les services actifs"""
    results = {
        'running': [],
        'failed': [],
        'enabled_at_boot': []
    }

    # Services actifs
    output, _ = run_cmd(["systemctl", "list-units", "--type=service", "--state=running", "--no-pager"])
    for line in output.split('\n'):
        if '.service' in line and 'loaded' in line:
            parts = line.split()
            if parts:
                results['running'].append(parts[0].replace('.service', ''))

    # Services échoués
    output, _ = run_cmd(["systemctl", "list-units", "--type=service", "--state=failed", "--no-pager"])
    for line in output.split('\n'):
        if '.service' in line:
            parts = line.split()
            if parts:
                results['failed'].append(parts[0].replace('.service', ''))

    return results

def full_audit(format_output="text"):
    """Audit complet de sécurité"""
    results = {
        'timestamp': datetime.now().isoformat(),
        'ssh': check_ssh_connections(),
        'ports': check_open_ports(),
        'firewall': check_firewall(),
        'users': check_users(),
        'processes': check_processes(),
        'permissions': check_permissions(),
        'services': check_services()
    }

    # Calculer le score de sécurité
    issues = 0
    critical = 0

    if not results['firewall']['enabled']:
        critical += 1
    if results['ports']['suspicious']:
        critical += len(results['ports']['suspicious'])
    if results['processes']['suspicious']:
        critical += len(results['processes']['suspicious'])
    if results['users']['suspicious_users']:
        critical += len(results['users']['suspicious_users'])
    if results['permissions']['world_writable']:
        issues += len(results['permissions']['world_writable'])
    if results['ssh']['auth_failures']:
        issues += 1

    results['summary'] = {
        'critical_issues': critical,
        'warnings': issues,
        'score': max(0, 100 - (critical * 20) - (issues * 5))
    }

    if format_output == "json":
        return json.dumps(results, indent=2, default=str)

    # Format texte
    output = []
    output.append("=" * 60)
    output.append("  AURA-OS SECURITY AUDITOR - RAPPORT")
    output.append("=" * 60)
    output.append(f"  Date: {results['timestamp'][:19]}")
    output.append("")

    # Score
    score = results['summary']['score']
    score_emoji = "🟢" if score >= 80 else "🟡" if score >= 50 else "🔴"
    output.append(f"  {score_emoji} SCORE DE SÉCURITÉ: {score}/100")
    output.append(f"     Critiques: {results['summary']['critical_issues']} | Warnings: {results['summary']['warnings']}")
    output.append("")

    # Firewall
    fw = results['firewall']
    fw_status = "✅ Actif" if fw['enabled'] else "❌ INACTIF"
    output.append(f"🛡️  FIREWALL: {fw_status}")
    output.append("-" * 40)
    if not fw['enabled']:
        output.append("   ⚠️  CRITIQUE: Activer le firewall avec 'sudo ufw enable'")
    output.append("")

    # SSH
    ssh = results['ssh']
    output.append(f"🔐 SSH")
    output.append("-" * 40)
    output.append(f"   Sessions actives: {len(ssh['active_sessions'])}")
    if ssh['active_sessions']:
        for s in ssh['active_sessions'][:3]:
            output.append(f"     • {s}")
    if ssh['auth_failures']:
        output.append(f"   ⚠️  Échecs d'auth récents: {len(ssh['auth_failures'])}")
    output.append("")

    # Ports
    ports = results['ports']
    output.append(f"🌐 PORTS OUVERTS: {len(ports['listening'])}")
    output.append("-" * 40)
    if ports['suspicious']:
        output.append("   ❌ PORTS SUSPECTS:")
        for p in ports['suspicious']:
            output.append(f"     • {p}")
    output.append(f"   Connexions établies: {len(ports['established'])}")
    output.append("")

    # Utilisateurs
    users = results['users']
    output.append(f"👤 UTILISATEURS")
    output.append("-" * 40)
    output.append(f"   Connectés: {len(users['logged_in'])}")
    output.append(f"   Sudo: {', '.join(users['sudo_users'])}")
    if users['suspicious_users']:
        output.append(f"   ❌ SUSPECTS (UID 0): {users['suspicious_users']}")
    output.append("")

    # Processus
    procs = results['processes']
    output.append(f"⚙️  PROCESSUS")
    output.append("-" * 40)
    output.append(f"   Avec réseau actif: {len(procs['network_active'])}")
    if procs['suspicious']:
        output.append("   ❌ SUSPECTS:")
        for p in procs['suspicious']:
            output.append(f"     • {p[:60]}")
    output.append("")

    # Permissions
    perms = results['permissions']
    output.append(f"🔑 PERMISSIONS")
    output.append("-" * 40)
    if perms['world_writable']:
        output.append(f"   ⚠️  Fichiers world-writable: {len(perms['world_writable'])}")
    if perms['suid_files']:
        output.append(f"   ⚠️  SUID non-standard: {len(perms['suid_files'])}")
    ssh_bad = [k for k in perms['ssh_keys'] if not k.get('ok', True)]
    if ssh_bad:
        output.append(f"   ⚠️  Clés SSH mal protégées: {[k['file'] for k in ssh_bad]}")
    output.append("")

    return '\n'.join(output)

def quick_check():
    """Vérification rapide"""
    output = []

    # Firewall
    fw = check_firewall()
    output.append(f"Firewall: {'✅' if fw['enabled'] else '❌'}")

    # SSH
    ssh = check_ssh_connections()
    output.append(f"Sessions: {len(ssh['active_sessions'])}")

    # Ports suspects
    ports = check_open_ports()
    output.append(f"Ports suspects: {len(ports['suspicious'])}")

    # Processus suspects
    procs = check_processes()
    output.append(f"Processus suspects: {len(procs['suspicious'])}")

    return '\n'.join(output)

def main():
    parser = argparse.ArgumentParser(
        description="AURA-OS Security Auditor - Audit de sécurité système",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s audit                 Audit complet
  %(prog)s audit --format json   Sortie JSON
  %(prog)s quick                 Vérification rapide
  %(prog)s ssh                   Vérifie SSH uniquement
  %(prog)s ports                 Vérifie les ports
  %(prog)s firewall              Vérifie le firewall
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commande")

    # Audit complet
    audit_parser = subparsers.add_parser("audit", help="Audit complet")
    audit_parser.add_argument("--format", choices=["text", "json"], default="text")

    # Quick check
    subparsers.add_parser("quick", help="Vérification rapide")

    # Checks individuels
    subparsers.add_parser("ssh", help="Vérifie SSH")
    subparsers.add_parser("ports", help="Vérifie les ports")
    subparsers.add_parser("firewall", help="Vérifie le firewall")
    subparsers.add_parser("users", help="Vérifie les utilisateurs")
    subparsers.add_parser("processes", help="Vérifie les processus")

    args = parser.parse_args()

    if args.command == "audit":
        print(full_audit(args.format))
        log_action('complete', 'Audit de sécurité terminé')

    elif args.command == "quick":
        print(quick_check())

    elif args.command == "ssh":
        result = check_ssh_connections()
        print(json.dumps(result, indent=2))

    elif args.command == "ports":
        result = check_open_ports()
        print(json.dumps(result, indent=2))

    elif args.command == "firewall":
        result = check_firewall()
        print(json.dumps(result, indent=2))

    elif args.command == "users":
        result = check_users()
        print(json.dumps(result, indent=2))

    elif args.command == "processes":
        result = check_processes()
        print(json.dumps(result, indent=2))

    else:
        print(full_audit())
        log_action('complete', 'Audit de sécurité terminé')

if __name__ == "__main__":
    main()
