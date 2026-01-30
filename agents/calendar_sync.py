#!/usr/bin/env python3
"""
AURA-OS Agent: Calendar Sync
Team: Info-Data
Description: Synchronisation calendrier - affiche événements ICS
"""
import argparse, json
from datetime import datetime
from pathlib import Path
try:
    import requests
except: requests = None

CONFIG_FILE = Path.home() / ".aura" / "calendar_config.json"

def load_config():
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {"ics_urls": []}

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def parse_ics(content):
    events = []
    ev = {}
    for line in content.split('\n'):
        l = line.strip()
        if l == "BEGIN:VEVENT": ev = {}
        elif l == "END:VEVENT" and ev: events.append(ev)
        elif ':' in l:
            k, v = l.split(':', 1)
            if k == "SUMMARY": ev["title"] = v
            elif k.startswith("DTSTART"): ev["start"] = v[:8]
    return events

def fetch_events():
    if not requests: return []
    events = []
    for url in load_config().get("ics_urls", []):
        try:
            events.extend(parse_ics(requests.get(url, timeout=10).text))
        except: pass
    return events

def main():
    parser = argparse.ArgumentParser(description="Calendar Sync Aura-OS")
    parser.add_argument("command", nargs="?", default="today", choices=["today", "week", "add", "config"])
    parser.add_argument("url", nargs="?")
    args = parser.parse_args()

    if args.command == "today":
        today = datetime.now().strftime("%Y%m%d")
        evs = [e for e in fetch_events() if e.get("start", "").startswith(today)]
        print(f"📅 {len(evs)} événement(s) aujourd'hui:")
        for e in evs: print(f"  • {e.get('title', '?')}")

    elif args.command == "week":
        evs = fetch_events()
        print(f"📅 {len(evs)} événement(s):")
        for e in evs[:10]: print(f"  • {e.get('start', '?')[:8]} - {e.get('title', '?')}")

    elif args.command == "add" and args.url:
        cfg = load_config()
        if args.url not in cfg["ics_urls"]:
            cfg["ics_urls"].append(args.url)
            save_config(cfg)
            print("✅ URL ajoutée")

    elif args.command == "config":
        print(json.dumps(load_config(), indent=2))

if __name__ == "__main__":
    main()
