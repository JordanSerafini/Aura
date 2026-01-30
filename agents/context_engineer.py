#!/usr/bin/env python3
"""Context Engineer Agent - Context packing et brain dump pour AURA."""
import argparse, ast, hashlib, os, re, sys
from datetime import datetime
from pathlib import Path
from typing import Optional

AURA_HOME = Path.home() / ".aura"
CONTEXT_DIR = AURA_HOME / "context"
TEMPLATES_DIR = CONTEXT_DIR / "templates"
SCRATCHPAD_DIR = CONTEXT_DIR / "scratchpad"
SUMMARIES_DIR = CONTEXT_DIR / "summaries"
SCRATCHPAD_FILE = SCRATCHPAD_DIR / "current_session.md"
CODE_EXTENSIONS = {'.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.cpp', '.h', '.rb', '.php'}

def ensure_dirs():
    for d in [CONTEXT_DIR, TEMPLATES_DIR, SCRATCHPAD_DIR, SUMMARIES_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def fmt(title: str, content: str, style: str = "info") -> str:
    icons = {"info": "i", "success": "+", "warning": "!", "error": "x"}
    return f"## [{icons.get(style, 'i')}] {title}\n\n{content}"

TEMPLATES = {
    "coding": """## Contexte de Developpement
### Objectif
{task}
### Structure de travail
1. Analyse des exigences
2. Conception de la solution
3. Implementation
4. Tests et validation
5. Documentation
### Points d'attention
- Conventions de code du projet
- Tests unitaires requis
- Documentation des fonctions publiques
- Gestion des erreurs
### Ressources
- Fichiers pertinents: [a identifier]
- Standards: PEP8 / ESLint selon langage""",
    "research": """## Contexte de Recherche
### Question principale
{task}
### Methodologie
1. Definir le perimetre de recherche
2. Identifier les sources fiables
3. Collecter les informations
4. Analyser et synthetiser
5. Documenter les conclusions
### Criteres d'evaluation
- Fiabilite des sources
- Actualite des informations
- Pertinence par rapport a l'objectif
### Format de sortie
- Resume executif
- Points cles detailles
- Sources et references""",
    "system": """## Contexte Administration Systeme
### Tache
{task}
### Checklist de securite
- [ ] Backup effectue si necessaire
- [ ] Permissions verifiees
- [ ] Impact sur autres services evalue
- [ ] Rollback plan defini
### Procedure
1. Verification etat actuel
2. Backup si necessaire
3. Execution des modifications
4. Validation du resultat
5. Documentation des changements""",
    "creative": """## Contexte Creatif
### Vision
{task}
### Parametres creatifs
- Ton: [a definir]
- Public cible: [a identifier]
- Contraintes: [a specifier]
### Processus creatif
1. Brainstorming initial
2. Exploration des idees
3. Selection et developpement
4. Raffinement
5. Finalisation
### Criteres de succes
- Originalite
- Coherence avec l'objectif
- Qualite d'execution"""
}

def cmd_prepare(args):
    """Genere un contexte optimise pour une tache."""
    template = TEMPLATES.get(args.type, TEMPLATES["coding"])
    context = template.format(task=args.task)
    header = f"""# Brain Dump - Session {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Type**: {args.type.upper()}
**Genere par**: Context Engineer Agent
---
"""
    output = header + context
    if SCRATCHPAD_FILE.exists():
        sp = SCRATCHPAD_FILE.read_text().strip()
        if sp:
            output += f"\n---\n## Notes de session (Scratchpad)\n{sp}\n"
    print(output)
    return 0

def extract_py_signatures(content: str) -> list:
    sigs = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                doc = (ast.get_docstring(node) or "").split('\n')[0][:80]
                prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                sig = f"{prefix}def {node.name}({', '.join(args)})"
                if doc: sig += f"  # {doc}"
                sigs.append(sig)
            elif isinstance(node, ast.ClassDef):
                bases = [b.id if isinstance(b, ast.Name) else "..." for b in node.bases]
                doc = (ast.get_docstring(node) or "").split('\n')[0][:80]
                sig = f"class {node.name}({', '.join(bases)})"
                if doc: sig += f"  # {doc}"
                sigs.append(sig)
    except SyntaxError:
        pass
    return sigs

def extract_js_signatures(content: str) -> list:
    sigs = []
    patterns = [
        r'(export\s+)?(async\s+)?function\s+(\w+)\s*\([^)]*\)',
        r'(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?\([^)]*\)\s*=>',
        r'(export\s+)?class\s+(\w+)(\s+extends\s+\w+)?',
    ]
    for p in patterns:
        for m in re.findall(p, content):
            sigs.append(' '.join(x for x in m if x).strip())
    return sigs[:50]

def compress_file(fp: Path) -> dict:
    result = {"path": str(fp), "size": fp.stat().st_size, "signatures": [], "summary": ""}
    try:
        content = fp.read_text(errors='ignore')
        lines = content.split('\n')
        result["lines"] = len(lines)
        if fp.suffix == '.py':
            result["signatures"] = extract_py_signatures(content)
        elif fp.suffix in {'.js', '.ts', '.tsx', '.jsx'}:
            result["signatures"] = extract_js_signatures(content)
        hdr = [l.strip() for l in lines[:20] if l.strip().startswith(('#', '//', '/*', '*', '"""', "'''"))]
        if hdr:
            result["summary"] = ' '.join(hdr[:3])[:200]
    except Exception as e:
        result["error"] = str(e)
    return result

def compress_dir(dp: Path) -> dict:
    result = {"path": str(dp), "structure": [], "files": [], "stats": {"total": 0, "code": 0, "lines": 0}}
    for root, dirs, files in os.walk(dp):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', '__pycache__', 'venv', '.git'}]
        rel = Path(root).relative_to(dp)
        lvl = len(rel.parts)
        if lvl <= 3:
            result["structure"].append("  " * lvl + f"{Path(root).name}/")
        for f in files:
            fp = Path(root) / f
            result["stats"]["total"] += 1
            if fp.suffix in CODE_EXTENSIONS:
                result["stats"]["code"] += 1
                c = compress_file(fp)
                if c.get("signatures"):
                    result["files"].append(c)
                result["stats"]["lines"] += c.get("lines", 0)
    return result

def cmd_compress(args):
    """Compresse fichiers/dossiers en extrayant signatures et resumes."""
    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        print(fmt("Erreur", f"Chemin non trouve: {path}", "error"))
        return 1
    if path.is_file():
        r = compress_file(path)
        out = f"# Compression: {path.name}\n\n- **Taille**: {r['size']} bytes\n- **Lignes**: {r.get('lines', 'N/A')}\n\n"
        if r.get("summary"): out += f"## Resume\n{r['summary']}\n\n"
        if r.get("signatures"): out += "## Signatures\n```\n" + '\n'.join(r["signatures"]) + "\n```\n"
    else:
        r = compress_dir(path)
        out = f"# Compression: {path.name}/\n\n## Statistiques\n- **Fichiers totaux**: {r['stats']['total']}\n"
        out += f"- **Fichiers de code**: {r['stats']['code']}\n- **Lignes de code**: {r['stats']['lines']}\n\n"
        out += "## Structure\n```\n" + '\n'.join(r["structure"][:50]) + "\n```\n\n"
        if r["files"]:
            out += "## Fichiers analyses\n\n"
            for f in r["files"][:20]:
                out += f"### {Path(f['path']).name}\n```\n" + '\n'.join(f["signatures"][:15]) + "\n```\n\n"
    if args.output:
        Path(args.output).expanduser().write_text(out)
        print(fmt("Succes", f"Compression sauvegardee: {args.output}", "success"))
    else:
        print(out)
    return 0

def cmd_scratchpad_add(args):
    ensure_dirs()
    ts = datetime.now().strftime('%H:%M:%S')
    note = f"- [{ts}] {args.note}\n"
    with open(SCRATCHPAD_FILE, 'a') as f:
        f.write(note)
    print(fmt("Note ajoutee", f"```\n{note.strip()}\n```", "success"))
    return 0

def cmd_scratchpad_show(args):
    if not SCRATCHPAD_FILE.exists() or not SCRATCHPAD_FILE.read_text().strip():
        print(fmt("Scratchpad", "_Aucune note dans cette session_", "info"))
    else:
        print(fmt("Scratchpad de session", SCRATCHPAD_FILE.read_text().strip(), "info"))
    return 0

def cmd_scratchpad_clear(args):
    if SCRATCHPAD_FILE.exists():
        SCRATCHPAD_FILE.unlink()
    print(fmt("Scratchpad", "Scratchpad vide avec succes", "success"))
    return 0

def cmd_summarize(args):
    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        print(fmt("Erreur", f"Chemin non trouve: {path}", "error"))
        return 1
    data = compress_dir(path) if path.is_dir() else compress_file(path)
    summary = f"# Resume: {path.name}\n\n**Chemin**: `{path}`\n**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    if path.is_dir():
        summary += f"## Vue d'ensemble\n\nCe projet contient **{data['stats']['total']}** fichiers "
        summary += f"dont **{data['stats']['code']}** fichiers de code totalisant **{data['stats']['lines']}** lignes.\n\n"
        summary += "## Structure principale\n```\n" + '\n'.join(data["structure"][:30]) + "\n```\n\n"
        if data["files"]:
            summary += "## Composants principaux\n\n"
            for f in data["files"][:10]:
                summary += f"- **{Path(f['path']).name}**: {len(f['signatures'])} fonctions/classes\n"
    else:
        summary += f"**Taille**: {data['size']} bytes\n**Lignes**: {data.get('lines', 'N/A')}\n\n"
        if data.get("signatures"):
            summary += "## API publique\n```\n" + '\n'.join(data["signatures"]) + "\n```\n"
    ensure_dirs()
    h = hashlib.md5(str(path).encode()).hexdigest()[:8]
    sf = SUMMARIES_DIR / f"{path.name}_{h}.md"
    sf.write_text(summary)
    print(summary + f"\n---\n_Resume sauvegarde: `{sf}`_")
    return 0

def cmd_template(args):
    tf = TEMPLATES_DIR / f"{args.type}_task.md"
    if not tf.exists():
        avail = [f.stem.replace('_task', '') for f in TEMPLATES_DIR.glob('*_task.md')]
        print(fmt("Erreur", f"Template non trouve: {args.type}\nDisponibles: {', '.join(avail)}", "error"))
        return 1
    print(tf.read_text())
    return 0

def main():
    p = argparse.ArgumentParser(description="Context Engineer - Context packing et brain dump pour AURA")
    sub = p.add_subparsers(dest="cmd", help="Commandes disponibles")
    
    pr = sub.add_parser("prepare", help="Generer un contexte optimise")
    pr.add_argument("--type", "-t", choices=["coding", "research", "system", "creative"], default="coding")
    pr.add_argument("--task", "-T", required=True, help="Description de la tache")
    pr.set_defaults(func=cmd_prepare)
    
    cp = sub.add_parser("compress", help="Compresser fichiers/dossiers")
    cp.add_argument("--path", "-p", required=True, help="Chemin a compresser")
    cp.add_argument("--output", "-o", help="Fichier de sortie")
    cp.set_defaults(func=cmd_compress)
    
    sp = sub.add_parser("scratchpad", help="Gerer le scratchpad de session")
    sps = sp.add_subparsers(dest="sp_cmd")
    add = sps.add_parser("add", help="Ajouter une note")
    add.add_argument("note", help="Note a ajouter")
    add.set_defaults(func=cmd_scratchpad_add)
    show = sps.add_parser("show", help="Afficher le scratchpad")
    show.set_defaults(func=cmd_scratchpad_show)
    clr = sps.add_parser("clear", help="Vider le scratchpad")
    clr.set_defaults(func=cmd_scratchpad_clear)
    
    sm = sub.add_parser("summarize", help="Resumer un projet")
    sm.add_argument("--path", "-p", required=True, help="Chemin a resumer")
    sm.set_defaults(func=cmd_summarize)
    
    tp = sub.add_parser("template", help="Afficher un template")
    tp.add_argument("--type", "-t", required=True, help="Type de template")
    tp.set_defaults(func=cmd_template)
    
    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 0
    if args.cmd == "scratchpad" and not args.sp_cmd:
        sp.print_help()
        return 0
    ensure_dirs()
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
