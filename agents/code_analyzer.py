#!/usr/bin/env python3
"""
AURA-OS Code Analyzer Agent
Analyse statique de code Python/JS/TS avec métriques
Team: core (dev workflows)
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from collections import defaultdict
from datetime import datetime


def analyze_python_file(filepath: Path) -> dict[str, Any]:
    """Analyse un fichier Python."""
    result = {
        "file": str(filepath),
        "type": "python",
        "lines": 0,
        "functions": [],
        "classes": [],
        "imports": [],
        "complexity": 0,
        "issues": [],
        "todos": []
    }

    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        result["lines"] = len(lines)

        # Parse AST
        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    result["functions"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": len(node.args.args),
                        "decorators": [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list[:3]]
                    })
                    # Complexité cyclomatique simplifiée
                    result["complexity"] += sum(1 for n in ast.walk(node) if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler)))

                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    result["classes"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods[:10]
                    })

                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            result["imports"].append(alias.name)
                    else:
                        result["imports"].append(node.module or "")

        except SyntaxError as e:
            result["issues"].append(f"Syntax error line {e.lineno}: {e.msg}")

        # Détection TODOs/FIXMEs
        for i, line in enumerate(lines, 1):
            if re.search(r'\b(TODO|FIXME|HACK|XXX)\b', line, re.IGNORECASE):
                result["todos"].append({"line": i, "text": line.strip()[:80]})

        # Issues de qualité simples
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                result["issues"].append(f"Line {i}: too long ({len(line)} chars)")
            if '\t' in line and '    ' in line:
                result["issues"].append(f"Line {i}: mixed tabs and spaces")

        result["issues"] = result["issues"][:10]
        result["todos"] = result["todos"][:10]

    except Exception as e:
        result["issues"].append(f"Error reading file: {e}")

    return result


def analyze_js_file(filepath: Path) -> dict[str, Any]:
    """Analyse basique d'un fichier JS/TS."""
    result = {
        "file": str(filepath),
        "type": "javascript" if filepath.suffix == '.js' else "typescript",
        "lines": 0,
        "functions": [],
        "classes": [],
        "imports": [],
        "issues": [],
        "todos": []
    }

    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        result["lines"] = len(lines)

        # Regex patterns pour JS/TS
        func_pattern = r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(|(\w+)\s*\([^)]*\)\s*(?:=>|{))'
        class_pattern = r'class\s+(\w+)'
        import_pattern = r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]'

        for match in re.finditer(func_pattern, content):
            name = match.group(1) or match.group(2) or match.group(3)
            if name and not name.startswith('_'):
                result["functions"].append({"name": name})

        for match in re.finditer(class_pattern, content):
            result["classes"].append({"name": match.group(1)})

        for match in re.finditer(import_pattern, content):
            result["imports"].append(match.group(1))

        # TODOs
        for i, line in enumerate(lines, 1):
            if re.search(r'\b(TODO|FIXME|HACK|XXX)\b', line, re.IGNORECASE):
                result["todos"].append({"line": i, "text": line.strip()[:80]})

        result["functions"] = result["functions"][:20]
        result["imports"] = result["imports"][:20]
        result["todos"] = result["todos"][:10]

    except Exception as e:
        result["issues"].append(f"Error: {e}")

    return result


def analyze_directory(path: Path, extensions: list[str] = None) -> dict[str, Any]:
    """Analyse un répertoire de code."""
    if extensions is None:
        extensions = ['.py', '.js', '.ts', '.tsx', '.jsx']

    exclude_dirs = {'node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build', '.git', '.next', 'target'}

    results = {
        "path": str(path),
        "analyzed_at": datetime.now().isoformat(),
        "summary": {
            "total_files": 0,
            "total_lines": 0,
            "total_functions": 0,
            "total_classes": 0,
            "total_issues": 0,
            "total_todos": 0,
            "languages": defaultdict(int)
        },
        "files": [],
        "top_issues": [],
        "all_todos": []
    }

    for filepath in path.rglob('*'):
        if filepath.suffix not in extensions:
            continue
        if any(excl in filepath.parts for excl in exclude_dirs):
            continue
        if not filepath.is_file():
            continue

        if filepath.suffix == '.py':
            file_result = analyze_python_file(filepath)
        elif filepath.suffix in ['.js', '.ts', '.tsx', '.jsx']:
            file_result = analyze_js_file(filepath)
        else:
            continue

        results["files"].append(file_result)
        results["summary"]["total_files"] += 1
        results["summary"]["total_lines"] += file_result.get("lines", 0)
        results["summary"]["total_functions"] += len(file_result.get("functions", []))
        results["summary"]["total_classes"] += len(file_result.get("classes", []))
        results["summary"]["total_issues"] += len(file_result.get("issues", []))
        results["summary"]["total_todos"] += len(file_result.get("todos", []))
        results["summary"]["languages"][file_result.get("type", "unknown")] += 1

        results["top_issues"].extend([{"file": str(filepath.name), "issue": i} for i in file_result.get("issues", [])])
        results["all_todos"].extend([{"file": str(filepath.name), **t} for t in file_result.get("todos", [])])

    results["summary"]["languages"] = dict(results["summary"]["languages"])
    results["top_issues"] = results["top_issues"][:20]
    results["all_todos"] = results["all_todos"][:30]

    return results


def print_report(results: dict[str, Any], verbose: bool = False):
    """Affiche un rapport formaté."""
    s = results["summary"]

    print(f"\n{'='*60}")
    print(f" Code Analysis Report")
    print(f" Path: {results['path']}")
    print(f"{'='*60}\n")

    print(f" Summary:")
    print(f"   Files analyzed: {s['total_files']}")
    print(f"   Total lines: {s['total_lines']:,}")
    print(f"   Functions: {s['total_functions']}")
    print(f"   Classes: {s['total_classes']}")
    print(f"   Issues found: {s['total_issues']}")
    print(f"   TODOs/FIXMEs: {s['total_todos']}")

    if s['languages']:
        print(f"\n Languages:")
        for lang, count in s['languages'].items():
            print(f"   {lang}: {count} files")

    if results['top_issues']:
        print(f"\n Top Issues:")
        for issue in results['top_issues'][:10]:
            print(f"   [{issue['file']}] {issue['issue']}")

    if results['all_todos']:
        print(f"\n TODOs/FIXMEs:")
        for todo in results['all_todos'][:10]:
            print(f"   [{todo['file']}:{todo['line']}] {todo['text'][:60]}")

    if verbose and results['files']:
        print(f"\n Files Detail:")
        for f in results['files'][:10]:
            funcs = len(f.get('functions', []))
            classes = len(f.get('classes', []))
            print(f"   {Path(f['file']).name}: {f['lines']} lines, {funcs} funcs, {classes} classes")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="AURA Code Analyzer")
    parser.add_argument("path", nargs="?", default=".", help="Path to analyze")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--ext", nargs="+", help="File extensions to analyze")

    args = parser.parse_args()
    path = Path(args.path).resolve()

    if not path.exists():
        print(f"Path not found: {path}")
        sys.exit(1)

    extensions = args.ext if args.ext else None
    results = analyze_directory(path, extensions)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print_report(results, args.verbose)


if __name__ == "__main__":
    main()
