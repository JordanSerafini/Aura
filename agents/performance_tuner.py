#!/usr/bin/env python3
"""
AURA-OS Agent: Performance Tuner
Team: PC-Admin
Description: Optimisation automatique du système
"""
import argparse, subprocess, os
from pathlib import Path

def get_governor():
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
            return f.read().strip()
    except: return "unknown"

def set_governor(gov):
    try:
        subprocess.run(["sudo", "cpupower", "frequency-set", "-g", gov], check=True)
        return True
    except: return False

def get_swappiness():
    try:
        with open("/proc/sys/vm/swappiness") as f:
            return int(f.read().strip())
    except: return -1

def clear_caches():
    try:
        subprocess.run(["sudo", "sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"], check=True)
        return True
    except: return False

def get_top_memory():
    result = subprocess.run(["ps", "aux", "--sort=-%mem"], capture_output=True, text=True)
    lines = result.stdout.strip().split('\n')[1:6]
    procs = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 11:
            procs.append({"pid": parts[1], "mem": parts[3], "cmd": parts[10]})
    return procs

def get_top_cpu():
    result = subprocess.run(["ps", "aux", "--sort=-%cpu"], capture_output=True, text=True)
    lines = result.stdout.strip().split('\n')[1:6]
    procs = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 11:
            procs.append({"pid": parts[1], "cpu": parts[2], "cmd": parts[10]})
    return procs

def analyze():
    issues = []
    swap = get_swappiness()
    if swap > 60:
        issues.append(f"Swappiness élevé ({swap}) - réduit les perfs")
    gov = get_governor()
    if gov == "powersave":
        issues.append("Governor en powersave - performances réduites")
    return issues

def optimize(aggressive=False):
    actions = []
    # Governor performance si aggressive
    if aggressive:
        if set_governor("performance"):
            actions.append("Governor → performance")
    # Clear caches
    if clear_caches():
        actions.append("Caches mémoire vidés")
    return actions

def main():
    parser = argparse.ArgumentParser(description="Performance Tuner Aura-OS")
    parser.add_argument("command", nargs="?", default="status", choices=["status", "analyze", "optimize", "top"])
    parser.add_argument("--aggressive", "-a", action="store_true")
    args = parser.parse_args()

    if args.command == "status":
        print("⚡ Performance Status:")
        print(f"  CPU Governor: {get_governor()}")
        print(f"  Swappiness: {get_swappiness()}")
        print("\n📊 Top CPU:")
        for p in get_top_cpu()[:3]:
            print(f"  {p['cpu']}% - {p['cmd'][:30]}")
        print("\n💾 Top RAM:")
        for p in get_top_memory()[:3]:
            print(f"  {p['mem']}% - {p['cmd'][:30]}")

    elif args.command == "analyze":
        issues = analyze()
        if issues:
            print("⚠️ Problèmes détectés:")
            for i in issues:
                print(f"  • {i}")
        else:
            print("✅ Système optimisé")

    elif args.command == "optimize":
        print("🔧 Optimisation..." + (" (aggressive)" if args.aggressive else ""))
        actions = optimize(aggressive=args.aggressive)
        for a in actions:
            print(f"  ✅ {a}")
        if not actions:
            print("  ℹ️ Rien à optimiser")

    elif args.command == "top":
        print("📊 Processus gourmands:")
        print("\nCPU:")
        for p in get_top_cpu():
            print(f"  {p['cpu']:>5}% [{p['pid']:>6}] {p['cmd'][:40]}")
        print("\nRAM:")
        for p in get_top_memory():
            print(f"  {p['mem']:>5}% [{p['pid']:>6}] {p['cmd'][:40]}")

if __name__ == "__main__":
    main()
