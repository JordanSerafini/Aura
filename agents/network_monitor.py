#!/usr/bin/env python3
"""
AURA-OS Agent: Network Monitor
Team: Cyber
Description: Surveillance réseau en temps réel
"""
import argparse, subprocess, json, re
from datetime import datetime

def get_connections():
    """Liste les connexions réseau actives"""
    conns = []
    try:
        out = subprocess.run(["ss", "-tunap"], capture_output=True, text=True).stdout
        for line in out.split('\n')[1:]:
            parts = line.split()
            if len(parts) >= 6:
                conns.append({
                    "proto": parts[0],
                    "state": parts[1] if parts[0] == "tcp" else "udp",
                    "local": parts[4] if len(parts) > 4 else "",
                    "remote": parts[5] if len(parts) > 5 else "",
                    "process": parts[-1] if "users:" in line else ""
                })
    except: pass
    return conns

def get_interfaces():
    """Info sur les interfaces réseau"""
    ifaces = {}
    try:
        out = subprocess.run(["ip", "-j", "addr"], capture_output=True, text=True).stdout
        data = json.loads(out)
        for iface in data:
            name = iface.get("ifname", "")
            addrs = [a.get("local","") for a in iface.get("addr_info", [])]
            ifaces[name] = {"state": iface.get("operstate",""), "addrs": addrs}
    except: pass
    return ifaces

def get_bandwidth():
    """Statistiques bande passante"""
    stats = {}
    try:
        with open("/proc/net/dev") as f:
            for line in f.readlines()[2:]:
                parts = line.split()
                iface = parts[0].rstrip(':')
                if iface != "lo":
                    stats[iface] = {
                        "rx_bytes": int(parts[1]),
                        "tx_bytes": int(parts[9]),
                        "rx_mb": round(int(parts[1]) / 1048576, 2),
                        "tx_mb": round(int(parts[9]) / 1048576, 2)
                    }
    except: pass
    return stats

def scan_ports(target="localhost"):
    """Scan rapide des ports ouverts"""
    open_ports = []
    try:
        out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True).stdout
        for line in out.split('\n')[1:]:
            match = re.search(r':(\d+)\s', line)
            if match: open_ports.append(int(match.group(1)))
    except: pass
    return sorted(set(open_ports))

def main():
    parser = argparse.ArgumentParser(description="Network Monitor Aura-OS")
    parser.add_argument("command", nargs="?", default="status",
                       choices=["status", "connections", "interfaces", "bandwidth", "ports", "watch"])
    parser.add_argument("--format", "-f", default="text", choices=["text", "json"])
    parser.add_argument("--filter", help="Filtrer par IP ou port")
    args = parser.parse_args()

    if args.command == "status":
        print(f"\n🌐 NETWORK STATUS - {datetime.now().strftime('%H:%M:%S')}")
        print("="*50)
        ifaces = get_interfaces()
        for name, info in ifaces.items():
            if info["addrs"]:
                print(f"  {name}: {info['state']} - {', '.join(info['addrs'])}")
        bw = get_bandwidth()
        print("\n📊 Bandwidth:")
        for iface, stats in bw.items():
            print(f"  {iface}: ↓{stats['rx_mb']}MB ↑{stats['tx_mb']}MB")
        ports = scan_ports()
        print(f"\n🔓 Ports ouverts: {', '.join(map(str, ports[:15]))}")
        conns = get_connections()
        print(f"📡 Connexions actives: {len(conns)}")

    elif args.command == "connections":
        conns = get_connections()
        if args.filter:
            conns = [c for c in conns if args.filter in str(c)]
        if args.format == "json":
            print(json.dumps(conns, indent=2))
        else:
            print(f"\n📡 {len(conns)} connexions actives:")
            for c in conns[:20]:
                print(f"  {c['proto']} {c['state']:12} {c['local']:25} → {c['remote'][:25]}")

    elif args.command == "interfaces":
        ifaces = get_interfaces()
        if args.format == "json":
            print(json.dumps(ifaces, indent=2))
        else:
            for name, info in ifaces.items():
                print(f"{name}: {info['state']} {info['addrs']}")

    elif args.command == "bandwidth":
        bw = get_bandwidth()
        if args.format == "json":
            print(json.dumps(bw, indent=2))
        else:
            for iface, stats in bw.items():
                print(f"{iface}: RX={stats['rx_mb']}MB TX={stats['tx_mb']}MB")

    elif args.command == "ports":
        ports = scan_ports()
        if args.format == "json":
            print(json.dumps(ports))
        else:
            print(f"Ports ouverts: {', '.join(map(str, ports))}")

if __name__ == "__main__":
    main()
