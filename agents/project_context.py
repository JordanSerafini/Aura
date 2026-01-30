#!/usr/bin/env python3
"""
AURA-OS Project Context Agent
Auto-détection du contexte projet (framework, langage, structure)
Team: core
"""

import argparse
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime

CONTEXT_CACHE = Path.home() / ".aura" / "context" / "projects.json"

# Signatures de détection de frameworks/langages
SIGNATURES = {
    # Python
    "python": {
        "files": ["*.py", "requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
        "dirs": ["venv", ".venv", "__pycache__"]
    },
    "django": {
        "files": ["manage.py", "settings.py"],
        "dirs": ["templates", "static"],
        "parent": "python"
    },
    "fastapi": {
        "files": ["main.py"],
        "content_hints": {"main.py": ["FastAPI", "from fastapi"]},
        "parent": "python"
    },
    "flask": {
        "files": ["app.py", "wsgi.py"],
        "content_hints": {"*.py": ["Flask", "from flask"]},
        "parent": "python"
    },

    # JavaScript/TypeScript
    "nodejs": {
        "files": ["package.json", "*.js", "*.mjs"],
        "dirs": ["node_modules"]
    },
    "typescript": {
        "files": ["tsconfig.json", "*.ts", "*.tsx"],
        "parent": "nodejs"
    },
    "react": {
        "files": ["*.jsx", "*.tsx"],
        "content_hints": {"package.json": ["react", "react-dom"]},
        "parent": "nodejs"
    },
    "vue": {
        "files": ["*.vue", "vue.config.js"],
        "content_hints": {"package.json": ["vue"]},
        "parent": "nodejs"
    },
    "nextjs": {
        "files": ["next.config.js", "next.config.mjs"],
        "dirs": [".next"],
        "parent": "react"
    },
    "nestjs": {
        "files": ["nest-cli.json"],
        "content_hints": {"package.json": ["@nestjs/core"]},
        "parent": "typescript"
    },

    # Rust
    "rust": {
        "files": ["Cargo.toml", "Cargo.lock", "*.rs"],
        "dirs": ["target", "src"]
    },

    # Go
    "go": {
        "files": ["go.mod", "go.sum", "*.go"],
        "dirs": ["pkg", "cmd"]
    },

    # DevOps
    "docker": {
        "files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"]
    },
    "kubernetes": {
        "files": ["*.yaml", "*.yml"],
        "content_hints": {"*.yaml": ["apiVersion:", "kind:"]},
        "dirs": ["k8s", "kubernetes", "manifests"]
    },

    # Data/ML
    "jupyter": {
        "files": ["*.ipynb"],
        "dirs": [".ipynb_checkpoints"]
    },
    "mlflow": {
        "files": ["MLproject", "mlflow.yaml"],
        "dirs": ["mlruns"]
    },

    # Misc
    "git": {
        "dirs": [".git"]
    }
}

def load_cache() -> dict:
    """Charge le cache des projets analysés"""
    if CONTEXT_CACHE.exists():
        return json.loads(CONTEXT_CACHE.read_text())
    return {"projects": {}}

def save_cache(data: dict):
    """Sauvegarde le cache"""
    CONTEXT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_CACHE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def glob_exists(path: Path, pattern: str) -> bool:
    """Vérifie si un pattern glob existe"""
    return bool(list(path.glob(pattern)))

def check_content_hints(path: Path, hints: dict) -> bool:
    """Vérifie les indices de contenu dans les fichiers"""
    for file_pattern, keywords in hints.items():
        for file_path in path.glob(file_pattern):
            if file_path.is_file():
                try:
                    content = file_path.read_text(errors='ignore')[:10000]
                    if any(kw in content for kw in keywords):
                        return True
                except:
                    pass
    return False

def detect_frameworks(path: Path) -> list:
    """Détecte les frameworks/langages d'un projet"""
    detected = []

    for framework, signature in SIGNATURES.items():
        score = 0
        max_score = 0

        # Check files
        if "files" in signature:
            max_score += len(signature["files"])
            for pattern in signature["files"]:
                if glob_exists(path, pattern):
                    score += 1

        # Check dirs
        if "dirs" in signature:
            max_score += len(signature["dirs"])
            for dirname in signature["dirs"]:
                if (path / dirname).is_dir():
                    score += 1

        # Check content hints
        if "content_hints" in signature:
            max_score += 2
            if check_content_hints(path, signature["content_hints"]):
                score += 2

        # Calcule la confiance
        if max_score > 0 and score > 0:
            confidence = score / max_score
            if confidence >= 0.3:  # Seuil minimum 30%
                detected.append({
                    "framework": framework,
                    "confidence": round(confidence, 2),
                    "parent": signature.get("parent")
                })

    # Trie par confiance
    detected.sort(key=lambda x: x["confidence"], reverse=True)
    return detected

def analyze_structure(path: Path) -> dict:
    """Analyse la structure du projet"""
    structure = {
        "total_files": 0,
        "total_dirs": 0,
        "file_types": {},
        "main_dirs": [],
        "size_mb": 0
    }

    exclude_dirs = {'.git', 'node_modules', '__pycache__', 'venv', '.venv',
                    'target', 'dist', 'build', '.next', '.cache'}

    for item in path.rglob("*"):
        rel_path = item.relative_to(path)

        # Skip excluded dirs
        if any(exc in rel_path.parts for exc in exclude_dirs):
            continue

        if item.is_file():
            structure["total_files"] += 1
            ext = item.suffix.lower() or "(no ext)"
            structure["file_types"][ext] = structure["file_types"].get(ext, 0) + 1
            try:
                structure["size_mb"] += item.stat().st_size / (1024 * 1024)
            except:
                pass
        elif item.is_dir():
            structure["total_dirs"] += 1
            if len(rel_path.parts) == 1:
                structure["main_dirs"].append(str(rel_path))

    structure["size_mb"] = round(structure["size_mb"], 2)

    # Top 5 extensions
    structure["file_types"] = dict(
        sorted(structure["file_types"].items(), key=lambda x: x[1], reverse=True)[:10]
    )

    return structure

def get_git_info(path: Path) -> dict | None:
    """Récupère les infos Git du projet"""
    git_dir = path / ".git"
    if not git_dir.is_dir():
        return None

    info = {}
    try:
        # Branch actuelle
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path, capture_output=True, text=True, timeout=5
        )
        info["branch"] = result.stdout.strip()

        # Remote origin
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path, capture_output=True, text=True, timeout=5
        )
        info["remote"] = result.stdout.strip() if result.returncode == 0 else None

        # Dernier commit
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H|%s|%ai"],
            cwd=path, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            if len(parts) == 3:
                info["last_commit"] = {
                    "hash": parts[0][:8],
                    "message": parts[1][:50],
                    "date": parts[2][:10]
                }

        # Status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path, capture_output=True, text=True, timeout=5
        )
        changes = result.stdout.strip().split('\n') if result.stdout.strip() else []
        info["uncommitted_changes"] = len(changes)

    except Exception as e:
        info["error"] = str(e)

    return info

def analyze_project(path: Path, use_cache: bool = True) -> dict:
    """Analyse complète d'un projet"""
    path = path.resolve()
    cache = load_cache()
    cache_key = str(path)

    # Vérifie le cache
    if use_cache and cache_key in cache["projects"]:
        cached = cache["projects"][cache_key]
        # Cache valide 1 heure
        if datetime.fromisoformat(cached["analyzed_at"]) > datetime.now().replace(hour=datetime.now().hour - 1):
            print(f"[i] Utilisation du cache pour {path.name}")
            return cached

    print(f"[*] Analyse de {path}...")

    context = {
        "path": str(path),
        "name": path.name,
        "analyzed_at": datetime.now().isoformat(),
        "frameworks": detect_frameworks(path),
        "structure": analyze_structure(path),
        "git": get_git_info(path)
    }

    # Détermine le type principal
    if context["frameworks"]:
        primary = context["frameworks"][0]
        context["primary_framework"] = primary["framework"]
        context["primary_confidence"] = primary["confidence"]
    else:
        context["primary_framework"] = "unknown"
        context["primary_confidence"] = 0

    # Sauvegarde dans le cache
    cache["projects"][cache_key] = context
    save_cache(cache)

    return context

def print_context(context: dict, verbose: bool = False):
    """Affiche le contexte de manière lisible"""
    print(f"\n{'='*60}")
    print(f" Projet: {context['name']}")
    print(f"{'='*60}")

    # Frameworks
    print(f"\n Frameworks détectés:")
    if context["frameworks"]:
        for fw in context["frameworks"][:5]:
            bar = "" * int(fw["confidence"] * 10)
            parent = f" ({fw['parent']})" if fw.get("parent") else ""
            print(f"   {fw['framework']:<15} {bar} {fw['confidence']*100:.0f}%{parent}")
    else:
        print("   (aucun détecté)")

    # Structure
    struct = context["structure"]
    print(f"\n Structure:")
    print(f"   Fichiers: {struct['total_files']}")
    print(f"   Dossiers: {struct['total_dirs']}")
    print(f"   Taille: {struct['size_mb']:.1f} MB")

    if verbose:
        print(f"\n Extensions:")
        for ext, count in list(struct["file_types"].items())[:5]:
            print(f"   {ext}: {count}")

        print(f"\n Dossiers principaux:")
        for d in struct["main_dirs"][:10]:
            print(f"   {d}/")

    # Git
    if context.get("git"):
        git = context["git"]
        print(f"\n Git:")
        print(f"   Branche: {git.get('branch', 'N/A')}")
        if git.get("remote"):
            print(f"   Remote: {git['remote'][:50]}")
        if git.get("last_commit"):
            lc = git["last_commit"]
            print(f"   Dernier commit: [{lc['hash']}] {lc['message']}")
        if git.get("uncommitted_changes", 0) > 0:
            print(f"   Changements non commités: {git['uncommitted_changes']}")

    print(f"\n{'='*60}\n")

def suggest_agents(context: dict) -> list:
    """Suggère les agents Claude appropriés pour ce projet"""
    suggestions = []

    framework_to_agents = {
        "python": ["backend-developer", "data-scientist"],
        "django": ["backend-developer", "database-architect"],
        "fastapi": ["backend-developer", "api-designer"],
        "flask": ["backend-developer", "api-designer"],
        "react": ["frontend-developer"],
        "vue": ["frontend-developer"],
        "nextjs": ["frontend-developer", "backend-developer"],
        "nestjs": ["backend-developer", "api-designer"],
        "typescript": ["frontend-developer", "backend-developer"],
        "rust": ["backend-developer"],
        "go": ["backend-developer", "devops-ml"],
        "docker": ["devops-ml"],
        "kubernetes": ["devops-ml"],
        "jupyter": ["data-scientist", "ml-engineer"],
        "mlflow": ["ml-engineer", "deep-learning"]
    }

    for fw in context["frameworks"]:
        if fw["framework"] in framework_to_agents:
            for agent in framework_to_agents[fw["framework"]]:
                if agent not in suggestions:
                    suggestions.append(agent)

    return suggestions[:5]

def main():
    parser = argparse.ArgumentParser(
        description="AURA Project Context - Auto-détection du contexte projet"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commandes")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyser un projet")
    analyze_parser.add_argument("path", nargs="?", default=".", help="Chemin du projet")
    analyze_parser.add_argument("--verbose", "-v", action="store_true")
    analyze_parser.add_argument("--no-cache", action="store_true")
    analyze_parser.add_argument("--json", action="store_true", help="Sortie JSON")

    # suggest
    suggest_parser = subparsers.add_parser("suggest", help="Suggérer des agents")
    suggest_parser.add_argument("path", nargs="?", default=".")

    # list
    subparsers.add_parser("list", help="Lister les projets analysés")

    # clear
    subparsers.add_parser("clear", help="Vider le cache")

    args = parser.parse_args()

    if args.command == "analyze" or args.command is None:
        path = Path(args.path if hasattr(args, 'path') else ".").resolve()
        if not path.is_dir():
            print(f"[-] Répertoire non trouvé: {path}")
            return

        context = analyze_project(path, use_cache=not getattr(args, 'no_cache', False))

        if getattr(args, 'json', False):
            print(json.dumps(context, indent=2, ensure_ascii=False))
        else:
            print_context(context, getattr(args, 'verbose', False))

    elif args.command == "suggest":
        path = Path(args.path).resolve()
        context = analyze_project(path)
        suggestions = suggest_agents(context)

        print(f"\n Agents suggérés pour {context['name']}:")
        if suggestions:
            for agent in suggestions:
                print(f"   - {agent}")
        else:
            print("   (aucune suggestion)")
        print()

    elif args.command == "list":
        cache = load_cache()
        if not cache["projects"]:
            print("[i] Aucun projet en cache")
            return

        print(f"\n{'='*60}")
        print(f"{'Projet':<30} {'Framework':<15} {'Analysé':<15}")
        print(f"{'='*60}")

        for path, ctx in cache["projects"].items():
            name = ctx["name"][:28]
            fw = ctx.get("primary_framework", "?")[:13]
            date = ctx["analyzed_at"][:10]
            print(f"{name:<30} {fw:<15} {date}")

        print(f"{'='*60}\n")

    elif args.command == "clear":
        if CONTEXT_CACHE.exists():
            CONTEXT_CACHE.unlink()
            print("[+] Cache vidé")
        else:
            print("[i] Cache déjà vide")

if __name__ == "__main__":
    main()
