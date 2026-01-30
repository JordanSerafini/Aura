#!/usr/bin/env python3
"""
AURA-OS Python Modern Auditor Agent
Audit Python moderne: Ruff, uv, type hints, async patterns 2026
Team: core (dev workflows)
Sources: astral-sh/ruff, uv, mypy, pyright, PEP 484/585/604
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict


class PythonModernAuditor:
    """Audit Python avec standards modernes 2026 (Ruff, uv, type hints)."""

    LEGACY_PATTERNS = {
        "critical": [
            (r'from\s+typing\s+import\s+(?:List|Dict|Set|Tuple|Optional|Union)\b',
             "Legacy typing import - use built-in types (list, dict, set | None)"),
            (r':\s*Optional\[', "X | None is deprecated - use 'X | None'"),
            (r':\s*Union\[', "X | Y is deprecated - use 'X | Y'"),
            (r'\bprint\s*\([^)]*\)\s*$', "Bare print() - use logging or rich"),
        ],
        "high": [
            (r'except\s*:', "Bare except clause - specify exception type"),
            (r'except\s+Exception\s*:', "Catching generic Exception - be specific"),
            (r'import\s+os\s*$', "Consider pathlib instead of os for path operations"),
            (r'open\s*\([^)]+\)(?!\s*as\s)', "open() without context manager"),
            (r'\.format\s*\(', "str.format() - prefer f-strings"),
            (r'%\s*\(', "%-formatting - prefer f-strings"),
            (r'time\.sleep\s*\(', "time.sleep() - consider asyncio.sleep() if async"),
        ],
        "medium": [
            (r'def\s+\w+\s*\([^)]*\)\s*:', "Function without return type hint"),
            (r'lambda\s+[^:]+:', "Lambda - consider named function for clarity"),
            (r'global\s+\w+', "Global variable - avoid mutable global state"),
            (r'exec\s*\(', "exec() is dangerous - avoid dynamic code execution"),
            (r'__import__\s*\(', "__import__() - use importlib"),
            (r'\.keys\(\)\s*\)', ".keys() often unnecessary in iteration"),
        ],
        "style": [
            (r'#\s*type:\s*ignore', "# type: ignore - add specific error code"),
            (r'#\s*noqa(?!:)', "# noqa without specific code"),
            (r'TODO|FIXME|HACK|XXX', "Code annotation needs attention"),
            (r'pass\s*$', "Empty pass statement"),
        ]
    }

    MODERN_TYPE_HINTS = {
        "list[": "list[",
        "dict[": "dict[",
        "set[": "set[",
        "tuple[": "tuple[",
        "type[": "type[",
        "frozenset[": "frozenset[",
        " | None": "",
        " | ": "" | }

    def __init__(self, path: Path, verbose: bool = False):
        self.path = path.resolve()
        self.verbose = verbose
        self.results: dict = {
            "path": str(self.path),
            "audited_at": datetime.now().isoformat(),
            "files_analyzed": 0,
            "total_lines": 0,
            "issues": defaultdict(list),
            "summary": {"critical": 0, "high": 0, "medium": 0, "style": 0},
            "type_coverage": {
                "functions_total": 0,
                "functions_typed": 0,
                "modern_types": 0,
                "legacy_types": 0
            },
            "tool_checks": {},
            "recommendations": [ | None
        }

    def analyze_type_hints(self, filepath: Path) -> dict:
        """Analyse les type hints d'un fichier."""
        stats = {"functions_total": 0, "functions_typed": 0, "modern": 0, "legacy": 0}
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    stats["functions_total" += 1
                    has_return_type = node.returns is not None
                    typed_args = sum(1 for arg in node.args.args if arg.annotation)
                    total_args = len(node.args.args)
                    if has_return_type and (total_args == 0 or typed_args == total_args):
                        stats["functions_typed"] += 1
            for modern, legacy in self.MODERN_TYPE_HINTS.items():
                stats["modern"] += content.count(modern)
                stats["legacy"] += content.count(legacy)
        except SyntaxError:
            pass
        except Exception as e:
            if self.verbose:
                print(f"Type analysis error {filepath}: {e}")
        return stats

    def analyze_file(self, filepath: Path) -> list:
        """Analyse un fichier Python."""
        issues = []
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            self.results["total_lines"] += len(lines)

            for severity, patterns in self.LEGACY_PATTERNS.items():
                for pattern, message in patterns:
                    for i, line in enumerate(lines, 1):
                        stripped = line.strip()
                        if stripped.startswith('#'):
                            if 'TODO' not in pattern and 'FIXME' not in pattern:
                                continue
                        if re.search(pattern, line):
                            issues.append({
                                "file": str(filepath.relative_to(self.path)),
                                "line": i,
                                "severity": severity,
                                "issue": message,
                                "code": line.strip()[:80]
                            })
                            self.results["summary"][severity] += 1

            type_stats = self.analyze_type_hints(filepath)
            self.results["type_coverage"]["functions_total"] += type_stats["functions_total"]
            self.results["type_coverage"]["functions_typed"] += type_stats["functions_typed"]
            self.results["type_coverage"]["modern_types"] += type_stats["modern"]
            self.results["type_coverage"]["legacy_types"] += type_stats["legacy"]
        except Exception as e:
            if self.verbose:
                print(f"Error analyzing {filepath}: {e}")
        return issues

    def check_pyproject(self) -> dict:
        """Vérifie pyproject.toml."""
        pyproject_path = self.path / "pyproject.toml"
        if not pyproject_path.exists():
            return {"exists": False, "issues": ["No pyproject.toml"]}
        content = pyproject_path.read_text()
        checks = {
            "ruff": "[tool.ruff]" in content,
            "mypy": "[tool.mypy]" in content,
            "pytest": "[tool.pytest" in content,
            "uv": "uv" in content.lower() or (self.path / "uv.lock").exists(),
            "black": "[tool.black]" in content,
        }
        issues = []
        recommendations = []
        if not checks["ruff"]:
            issues.append("Ruff not configured")
            recommendations.append("Ruff replaces Black, isort, Flake8 with 10-100x speed")
        if checks["black"]:
            issues.append("Black detected - consider migrating to Ruff format")
        if not checks["mypy"]:
            issues.append("MyPy not configured")
        if not checks["uv"]:
            recommendations.append("Consider uv for faster package management")
        return {"exists": True, "checks": checks, "issues": issues, "recommendations": recommendations}

    def check_ruff_config(self) -> dict:
        """Vérifie la config Ruff."""
        ruff_toml = self.path / "ruff.toml"
        pyproject = self.path / "pyproject.toml"
        config_content = ""
        config_file = None
        if ruff_toml.exists():
            config_content = ruff_toml.read_text()
            config_file = "ruff.toml"
        elif pyproject.exists():
            content = pyproject.read_text()
            if "[tool.ruff]" in content:
                config_content = content
                config_file = "pyproject.toml"
        if not config_content:
            return {"configured": False}
        recommended_rules = ["E", "F", "I", "B", "C4", "UP", "ANN", "ASYNC", "S", "PTH"]
        enabled_rules = []
        for rule in recommended_rules:
            if f'"{rule}"' in config_content or f"'{rule}'" in config_content:
                enabled_rules.append(rule)
        return {
            "configured": True,
            "file": config_file,
            "enabled_rules": enabled_rules,
            "recommended_missing": [r for r in recommended_rules if r not in enabled_rules],
            "target_version": "py312" if "py312" in config_content else "unknown"
        }

    def run_ruff(self) -> dict | None:
        """Exécute Ruff si disponible."""
        try:
            result = subprocess.run(
                ["ruff", "check", ".", "--output-format", "json"],
                cwd=self.path, capture_output=True, text=True, timeout=30
            )
            if result.stdout:
                issues = json.loads(result.stdout)
                return {"count": len(issues), "sample": issues[:5]}
        except FileNotFoundError:
            return {"available": False}
        except Exception as e:
            return {"error": str(e)}
        return None

    def audit(self) -> dict:
        """Lance l'audit complet."""
        self.results["tool_checks"]["pyproject"] = self.check_pyproject()
        self.results["tool_checks"]["ruff"] = self.check_ruff_config()
        ruff_result = self.run_ruff()
        if ruff_result:
            self.results["tool_checks"]["ruff_scan"] = ruff_result

        exclude_dirs = {'venv', '.venv', '__pycache__', '.git', 'node_modules',
                        'dist', 'build', '.mypy_cache', '.ruff_cache', 'site-packages'}
        for filepath in self.path.rglob('*.py'):
            if any(excl in filepath.parts for excl in exclude_dirs):
                continue
            issues = self.analyze_file(filepath)
            for issue in issues:
                self.results["issues"][issue["severity"]].append(issue)
            self.results["files_analyzed"] += 1

        tc = self.results["type_coverage"]
        if tc["functions_total"] > 0:
            tc["coverage_percent"] = round(tc["functions_typed"] / tc["functions_total"] * 100, 1)
        self._generate_recommendations()
        return self.results

    def _generate_recommendations(self):
        """Génère des recommandations."""
        recs = []
        tc = self.results["type_coverage"]
        coverage = tc.get("coverage_percent", 0)
        if coverage < 50:
            recs.append(f"Type coverage is {coverage}% - aim for >80% for production code")
        if tc["legacy_types"] > tc["modern_types"]:
            recs.append("Use modern type hints: list[] instead of list[], X | None instead of X | None")
        if self.results["summary"]["critical"] > 0:
            recs.append("Update deprecated typing imports to modern syntax (Python 3.10+)")
        pyproject = self.results["tool_checks"].get("pyproject", {})
        if pyproject.get("recommendations"):
            recs.extend(pyproject["recommendations"])
        ruff = self.results["tool_checks"].get("ruff", {})
        if ruff.get("recommended_missing"):
            recs.append(f"Enable Ruff rules: {', '.join(ruff['recommended_missing'][:5])}")
        if not recs:
            recs.append("Code follows modern Python best practices - excellent!")
        self.results["recommendations"] = recs


def print_report(results: dict, verbose: bool = False):
    """Affiche le rapport."""
    print(f"\n{'='*60}")
    print(f" Python Modern Audit Report (2026 Standards)")
    print(f" Path: {results['path']}")
    print(f"{'='*60}\n")
    s = results["summary"]
    total = sum(s.values())
    print(f" Summary:")
    print(f"   Files: {results['files_analyzed']} | Lines: {results['total_lines']:,}")
    print(f"   Issues: {total} (Critical: {s['critical']}, High: {s['high']}, Medium: {s['medium']}, Style: {s['style']})")
    tc = results["type_coverage"]
    if tc["functions_total"] > 0:
        print(f"\n Type Coverage:")
        print(f"   Functions: {tc['functions_typed']}/{tc['functions_total']} typed ({tc.get('coverage_percent', 0)}%)")
        print(f"   Modern types: {tc['modern_types']} | Legacy types: {tc['legacy_types']}")
    print(f"\n Tool Configuration:")
    pyproject = results["tool_checks"].get("pyproject", {})
    print(f"   pyproject.toml: {'Exists' if pyproject.get('exists') else 'Missing'}")
    ruff = results["tool_checks"].get("ruff", {})
    print(f"   Ruff: {'Configured' if ruff.get('configured') else 'Not configured'}")
    if ruff.get("enabled_rules"):
        print(f"     Enabled: {', '.join(ruff['enabled_rules'][:8])}")
    if results["issues"].get("critical"):
        print(f"\n Critical Issues (legacy patterns):")
        for issue in list(results["issues"]["critical"])[:10]:
            print(f"   [{issue['file']}:{issue['line']}] {issue['issue']}")
    if results["issues"].get("high") and verbose:
        print(f"\n High Severity Issues:")
        for issue in list(results["issues"]["high"])[:10]:
            print(f"   [{issue['file']}:{issue['line']}] {issue['issue']}")
    if results.get("recommendations"):
        print(f"\n Recommendations (2026 Best Practices):")
        for rec in results["recommendations"]:
            print(f"   * {rec}")
    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="AURA Python Modern Auditor")
    parser.add_argument("path", nargs="?", default=".", help="Path to audit")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = Path(args.path)
    if not path.exists():
        print(f"Path not found: {path}")
        sys.exit(1)
    auditor = PythonModernAuditor(path, verbose=args.verbose)
    results = auditor.audit()
    if args.json:
        print(json.dumps(results, indent=2, default=list))
    else:
        print_report(results, verbose=args.verbose)


if __name__ == "__main__":
    main()
