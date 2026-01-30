#!/usr/bin/env python3
"""
AURA Context Loader - Charge automatiquement le contexte d'un projet
Détecte le type de projet et génère un résumé pour Claude
"""

import json
import os
from pathlib import Path

def detect_project_type(project_path):
    """Détecte le type de projet basé sur les fichiers présents"""
    path = Path(project_path)
    types = []
    
    # Python
    if (path / "requirements.txt").exists() or (path / "pyproject.toml").exists():
        types.append("python")
    if (path / "setup.py").exists():
        types.append("python-package")
    
    # Node.js
    if (path / "package.json").exists():
        types.append("nodejs")
        pkg = json.loads((path / "package.json").read_text())
        if "react" in pkg.get("dependencies", {}):
            types.append("react")
        if "vue" in pkg.get("dependencies", {}):
            types.append("vue")
        if "next" in pkg.get("dependencies", {}):
            types.append("nextjs")
    
    # Databases
    if (path / "docker-compose.yml").exists() or (path / "docker-compose.yaml").exists():
        types.append("docker")
    if list(path.glob("**/migrations/*.py")) or list(path.glob("**/migrations/*.sql")):
        types.append("database")
    
    # ML/Data
    if list(path.glob("**/*.ipynb")):
        types.append("jupyter")
    if (path / "model").exists() or list(path.glob("**/*.pkl")) or list(path.glob("**/*.pt")):
        types.append("ml")
    
    # Git
    if (path / ".git").exists():
        types.append("git")
    
    return types

def get_project_structure(project_path, max_depth=3):
    """Génère la structure du projet"""
    path = Path(project_path)
    structure = []
    
    ignore_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', '.cache', 'dist', 'build'}
    ignore_files = {'.DS_Store', 'package-lock.json', 'yarn.lock'}
    
    def walk(p, depth=0):
        if depth > max_depth:
            return
        try:
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            for item in items:
                if item.name in ignore_dirs or item.name in ignore_files:
                    continue
                if item.name.startswith('.') and item.is_dir():
                    continue
                
                prefix = "  " * depth
                if item.is_dir():
                    structure.append(f"{prefix}{item.name}/")
                    walk(item, depth + 1)
                else:
                    structure.append(f"{prefix}{item.name}")
        except PermissionError:
            pass
    
    walk(path)
    return structure[:100]  # Limiter à 100 lignes

def generate_context(project_path):
    """Génère le contexte complet pour un projet"""
    path = Path(project_path).resolve()
    
    context = {
        "path": str(path),
        "name": path.name,
        "types": detect_project_type(path),
        "structure": get_project_structure(path),
        "key_files": []
    }
    
    # Fichiers clés à lire
    key_files = [
        "README.md", "README.rst", "readme.md",
        "package.json", "pyproject.toml", "requirements.txt",
        "Makefile", "Dockerfile", "docker-compose.yml",
        ".env.example", "config.yaml", "config.json"
    ]
    
    for kf in key_files:
        kf_path = path / kf
        if kf_path.exists():
            context["key_files"].append(kf)
    
    return context

def format_for_claude(context):
    """Formate le contexte pour être passé à Claude"""
    lines = [
        f"# Projet: {context['name']}",
        f"**Chemin**: `{context['path']}`",
        f"**Types détectés**: {', '.join(context['types']) or 'inconnu'}",
        "",
        "## Structure:",
        "```",
    ]
    lines.extend(context['structure'][:50])
    lines.append("```")
    
    if context['key_files']:
        lines.append("")
        lines.append(f"## Fichiers clés: {', '.join(context['key_files'])}")
    
    return "\n".join(lines)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AURA Context Loader")
    parser.add_argument("path", nargs="?", default=".", help="Chemin du projet")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()
    
    context = generate_context(args.path)
    
    if args.json:
        print(json.dumps(context, indent=2))
    else:
        print(format_for_claude(context))

if __name__ == "__main__":
    main()
