#!/usr/bin/env python3
"""
AURA-OS Agent: Tech Watcher
Team: Info-Data
Description: Veille technologique - scrape HN, Lobsters, Reddit
"""
import argparse, json, sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ pip install requests"); sys.exit(1)

HEADERS = {"User-Agent": "Aura-OS/1.0"}

def fetch_hn(limit=10):
    stories = []
    try:
        ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10).json()[:limit]
        for i in ids:
            item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json", timeout=5).json()
            if item: stories.append({"title": item.get("title",""), "score": item.get("score",0), "url": item.get("url",""), "source": "HN"})
    except: pass
    return stories

def fetch_lobsters(limit=10):
    stories = []
    try:
        for item in requests.get("https://lobste.rs/hottest.json", timeout=10).json()[:limit]:
            stories.append({"title": item.get("title",""), "score": item.get("score",0), "url": item.get("url",""), "source": "Lobsters"})
    except: pass
    return stories

def fetch_reddit(sub, limit=10):
    stories = []
    try:
        data = requests.get(f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}", headers=HEADERS, timeout=10).json()
        for p in data.get("data",{}).get("children",[]):
            d = p.get("data",{})
            if not d.get("stickied"): stories.append({"title": d.get("title",""), "score": d.get("score",0), "url": d.get("url",""), "source": f"r/{sub}"})
    except: pass
    return stories

def main():
    parser = argparse.ArgumentParser(description="Veille tech Aura-OS")
    parser.add_argument("command", nargs="?", default="fetch", choices=["fetch", "save"])
    parser.add_argument("--source", "-s", default="all", choices=["all", "hn", "lobsters", "reddit"])
    parser.add_argument("--limit", "-l", type=int, default=10)
    parser.add_argument("--top", "-t", type=int, default=15)
    parser.add_argument("--format", "-f", default="text", choices=["text", "json"])
    args = parser.parse_args()

    print("📡 Récupération des news tech...")
    stories = []
    if args.source in ["all", "hn"]: stories += fetch_hn(args.limit)
    if args.source in ["all", "lobsters"]: stories += fetch_lobsters(args.limit)
    if args.source in ["all", "reddit"]:
        stories += fetch_reddit("linux", args.limit)
        stories += fetch_reddit("programming", args.limit)

    stories = sorted(stories, key=lambda x: x.get("score",0), reverse=True)[:args.top]

    if args.format == "json":
        print(json.dumps(stories, indent=2))
    else:
        print(f"\n🔥 TOP {len(stories)} NEWS - {datetime.now().strftime('%H:%M')}")
        print("="*60)
        for i, s in enumerate(stories, 1):
            hot = "🔥" if s["score"] > 200 else ""
            print(f"{i:2}. [{s['source']}] {hot} {s['title'][:60]}")
            print(f"    ⬆️ {s['score']} | {s['url'][:50]}...")

    if args.command == "save":
        log_dir = Path.home() / "aura_logs" / datetime.now().strftime("%Y-%m-%d")
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "info-data.md", "a") as f:
            f.write(f"\n## Veille {datetime.now().strftime('%H:%M')}\n")
            for s in stories[:10]: f.write(f"- [{s['source']}] {s['title']}\n")
        print(f"\n✅ Sauvegardé dans les logs")

if __name__ == "__main__":
    main()
