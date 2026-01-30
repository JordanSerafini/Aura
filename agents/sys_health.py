#!/usr/bin/env python3
"""
AURA-OS Agent: System Health Monitor
Team: PC-Admin
Description: Vérifie l'état du système (CPU, RAM, températures)
Cache: 5 minutes (--force pour ignorer)
"""

import argparse
import json
import subprocess
import os
import sys
import time
from pathlib import Path

# Import du cache manager
sys.path.insert(0, str(Path(__file__).parent))
try:
    from utils.cache_manager import get_cached, set_cache, is_cache_valid
except ImportError:
    # Fallback si le module n'est pas disponible
    def get_cached(key, max_age_seconds=300):
        return None
    def set_cache(key, data):
        return False
    def is_cache_valid(key, max_age_seconds=300):
        return False

# Configuration du cache
CACHE_KEY = "sys_health"
CACHE_FILE = Path("/tmp/aura_cache_sys_health.json")
CACHE_MAX_AGE = 300  # 5 minutes

def get_cpu_usage():
    """Récupère l'utilisation CPU via /proc/stat."""
    try:
        result = subprocess.run(
            ["grep", "-c", "^processor", "/proc/cpuinfo"],
            capture_output=True, text=True
        )
        cpu_count = int(result.stdout.strip())

        result = subprocess.run(
            ["awk", '{u=$2+$4; t=$2+$4+$5; if (NR==1){u1=u; t1=t;} else print ($2+$4-u1) * 100 / (t-t1)}',
             "/proc/stat", "/proc/stat"],
            capture_output=True, text=True, shell=False
        )
        # Méthode alternative plus fiable
        result = subprocess.run(
            ["top", "-bn1"],
            capture_output=True, text=True
        )
        for line in result.stdout.split('\n'):
            if 'Cpu(s)' in line or '%Cpu' in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if 'us' in part or (i > 0 and 'us' in parts[i-1] if i > 0 else False):
                        try:
                            usage = float(parts[i-1].replace(',', '.'))
                            return {"percent": usage, "cores": cpu_count}
                        except:
                            pass
                # Fallback: extraire le premier nombre
                import re
                numbers = re.findall(r'[\d,]+\.?\d*', line)
                if numbers:
                    return {"percent": float(numbers[0].replace(',', '.')), "cores": cpu_count}

        return {"percent": 0.0, "cores": cpu_count}
    except Exception as e:
        return {"error": str(e)}

def get_memory_usage():
    """Récupère l'utilisation mémoire via /proc/meminfo."""
    try:
        meminfo = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                key = parts[0].rstrip(':')
                value = int(parts[1])
                meminfo[key] = value

        total = meminfo.get('MemTotal', 0) / 1024 / 1024  # GB
        available = meminfo.get('MemAvailable', 0) / 1024 / 1024  # GB
        used = total - available
        percent = (used / total) * 100 if total > 0 else 0

        return {
            "total_gb": round(total, 2),
            "used_gb": round(used, 2),
            "available_gb": round(available, 2),
            "percent": round(percent, 1)
        }
    except Exception as e:
        return {"error": str(e)}

def get_temperatures():
    """Récupère les températures via les fichiers hwmon."""
    temps = []
    hwmon_base = Path("/sys/class/hwmon")

    if not hwmon_base.exists():
        return {"error": "hwmon not available"}

    try:
        for hwmon in hwmon_base.iterdir():
            name_file = hwmon / "name"
            if name_file.exists():
                name = name_file.read_text().strip()
            else:
                name = hwmon.name

            # Chercher les fichiers temp*_input
            for temp_file in hwmon.glob("temp*_input"):
                try:
                    temp_c = int(temp_file.read_text().strip()) / 1000
                    label_file = temp_file.with_name(temp_file.name.replace("_input", "_label"))
                    if label_file.exists():
                        label = label_file.read_text().strip()
                    else:
                        label = temp_file.stem

                    temps.append({
                        "sensor": name,
                        "label": label,
                        "celsius": round(temp_c, 1)
                    })
                except:
                    pass
    except Exception as e:
        return {"error": str(e)}

    return temps if temps else {"info": "Aucun capteur trouvé"}

def get_disk_usage():
    """Récupère l'usage disque."""
    try:
        result = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True
        )
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 2:
            parts = lines[1].split()
            return {
                "device": parts[0],
                "total": parts[1],
                "used": parts[2],
                "available": parts[3],
                "percent": parts[4]
            }
    except Exception as e:
        return {"error": str(e)}

def generate_report(output_format="text", force_refresh=False):
    """Génère un rapport complet de santé système.

    Args:
        output_format: 'text' ou 'json'
        force_refresh: Si True, ignore le cache
    """
    report = None
    from_cache = False

    # Essayer de recuperer depuis le cache (sauf si force)
    if not force_refresh:
        cached_report = get_cached(CACHE_KEY, CACHE_MAX_AGE)
        if cached_report is not None:
            report = cached_report
            from_cache = True

    # Generer un nouveau rapport si necessaire
    if report is None:
        cpu = get_cpu_usage()
        memory = get_memory_usage()
        temps = get_temperatures()
        disk = get_disk_usage()

        report = {
            "cpu": cpu,
            "memory": memory,
            "temperatures": temps,
            "disk": disk,
            "timestamp": time.time()
        }

        # Sauvegarder dans le cache
        set_cache(CACHE_KEY, report)

    # Ajouter l'indicateur de cache au rapport
    report["from_cache"] = from_cache

    if output_format == "json":
        return json.dumps(report, indent=2, ensure_ascii=False)
    else:
        # Format texte lisible
        cpu = report.get("cpu", {})
        memory = report.get("memory", {})
        temps = report.get("temperatures", [])
        disk = report.get("disk", {})

        cache_indicator = " [CACHE]" if from_cache else " [LIVE]"
        lines = [f"═══ AURA-OS System Health Report ═══{cache_indicator}", ""]

        # CPU
        lines.append(f"🖥️  CPU: {cpu.get('percent', 'N/A')}% ({cpu.get('cores', '?')} cores)")

        # RAM
        lines.append(f"🧠 RAM: {memory.get('percent', 'N/A')}% ({memory.get('used_gb', '?')}/{memory.get('total_gb', '?')} GB)")

        # Températures
        if isinstance(temps, list) and temps:
            lines.append("🌡️  Températures:")
            for t in temps[:5]:  # Max 5 capteurs
                lines.append(f"   - {t['sensor']}/{t['label']}: {t['celsius']}°C")
        else:
            lines.append("🌡️  Températures: Non disponible")

        # Disque
        lines.append(f"💾 Disque /: {disk.get('percent', 'N/A')} utilisé ({disk.get('used', '?')}/{disk.get('total', '?')})")

        # Status global
        status = "🟢 HEALTHY"
        if memory.get('percent', 0) > 90:
            status = "🔴 CRITICAL - RAM"
        elif cpu.get('percent', 0) > 90:
            status = "🟠 WARNING - CPU"
        elif any(isinstance(temps, list) and t.get('celsius', 0) > 80 for t in (temps if isinstance(temps, list) else [])):
            status = "🟠 WARNING - TEMP"

        lines.append(f"\n📊 Status: {status}")

        return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="AURA-OS System Health Agent")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="Format de sortie")
    parser.add_argument("--component", choices=["cpu", "memory", "temps", "disk", "all"],
                        default="all", help="Composant à vérifier")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Ignorer le cache et forcer un rafraichissement")
    parser.add_argument("--cache-info", action="store_true",
                        help="Afficher les informations du cache")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Vider le cache")

    args = parser.parse_args()

    # Gestion des options de cache
    if args.cache_info:
        try:
            from utils.cache_manager import get_cache_info
            info = get_cache_info(CACHE_KEY)
            print(json.dumps(info, indent=2))
        except ImportError:
            print('{"error": "Cache manager not available"}')
        return

    if args.clear_cache:
        try:
            from utils.cache_manager import clear_cache
            deleted = clear_cache(CACHE_KEY)
            print(f"Cache cleared: {deleted} file(s) deleted")
        except ImportError:
            # Fallback: supprimer directement
            if CACHE_FILE.exists():
                CACHE_FILE.unlink()
                print("Cache cleared: 1 file deleted")
            else:
                print("Cache cleared: 0 files deleted")
        return

    if args.component == "all":
        print(generate_report(args.format, force_refresh=args.force))
    else:
        # Pour les composants individuels, pas de cache
        funcs = {
            "cpu": get_cpu_usage,
            "memory": get_memory_usage,
            "temps": get_temperatures,
            "disk": get_disk_usage
        }
        result = funcs[args.component]()
        if args.format == "json":
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result)

if __name__ == "__main__":
    main()
