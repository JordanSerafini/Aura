#!/usr/bin/env python3
"""
AURA-OS TypeScript Strict Auditor Agent
Audit TypeScript ultra-strict: types, any, eslint, patterns 2026
Team: core (dev workflows)
Sources: typescript-eslint, ts-strict/eslint-config, ESLint 9 flat config
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from collections import defaultdict


class TSStrictAuditor:
    """Audit TypeScript avec règles strictes 2026."""

    # Patterns à détecter (du plus critique au moins critique)
    STRICT_PATTERNS = {
        "critical": [
            (r':\s*any\b', "Explicit 'any' type - use 'unknown' or proper type"),
            (r'as\s+any\b', "Type assertion to 'any' - unsafe cast"),
            (r'@ts-ignore', "@ts-ignore bypasses type checking"),
            (r'@ts-nocheck', "@ts-nocheck disables all type checking"),
            (r'@ts-expect-error(?!\s*:)', "@ts-expect-error without description"),
            (r'eval\s*\(', "eval() is dangerous and prevents optimization"),
        ],
        "high": [
            (r'!\s*\.', "Non-null assertion (!) - prefer optional chaining"),
            (r'as\s+\w+(?:\[\])?(?:\s*\|\s*\w+)*\s*[;\)\n]', "Type assertion - prefer type guards"),
            (r'Function\b(?!\w)', "Generic 'Function' type - use specific signature"),
            (r'Object\b(?!\w)', "Generic 'Object' type - use Record or interface"),
            (r'\[\s*\.\.\.\w+\s*\]', "Spread in array literal - check performance"),
            (r'console\.(log|debug|info)\s*\(', "Console statement in production code"),
        ],
        "medium": [
            (r'\?\?=|\|\|=|&&=', "Logical assignment - check browser support"),
            (r'require\s*\(', "CommonJS require - prefer ES imports"),
            (r'module\.exports', "CommonJS exports - prefer ES exports"),
            (r'export\s+default', "Default export - prefer named exports"),
            (r'==(?!=)', "Loose equality - use strict equality (===)"),
            (r'!=(?!=)', "Loose inequality - use strict inequality (!==)"),
        ],
        "low": [
            (r'TODO|FIXME|HACK|XXX', "Code annotation needs attention"),
            (r'\/\/\s*$', "Empty comment"),
            (r'{\s*}', "Empty block"),
        ]
    }

    def __init__(self, path: Path, verbose: bool = False):
        self.path = path.resolve()
        self.verbose = verbose
        self.results: dict[str, Any] = {
            "path": str(self.path),
            "audited_at": datetime.now().isoformat(),
            "files_analyzed": 0,
            "issues": defaultdict(list),
            "summary": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0
            },
            "tsconfig_check": None,
            "eslint_check": None,
            "recommendations": []
        }

    def analyze_file(self, filepath: Path) -> list[Dict]:
        """Analyse un fichier TS."""
        issues = []
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')

            for severity, patterns in self.STRICT_PATTERNS.items():
                for pattern, message in patterns:
                    for i, line in enumerate(lines, 1):
                        # Skip comments for some patterns
                        stripped = line.strip()
                        if stripped.startswith('//') or stripped.startswith('/*'):
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
        except Exception as e:
            if self.verbose:
                print(f"Error analyzing {filepath}: {e}")

        return issues

    def check_tsconfig(self) -> dict[str, Any]:
        """Vérifie la configuration TypeScript."""
        tsconfig_path = self.path / "tsconfig.json"
        if not tsconfig_path.exists():
            return {"exists": False, "strict": False, "issues": ["No tsconfig.json found"]}

        try:
            config = json.loads(tsconfig_path.read_text())
            compiler_opts = config.get("compilerOptions", {})

            # Règles strictes recommandées 2026
            strict_rules = {
                "strict": True,
                "noImplicitAny": True,
                "strictNullChecks": True,
                "strictFunctionTypes": True,
                "strictBindCallApply": True,
                "strictPropertyInitialization": True,
                "noImplicitThis": True,
                "useUnknownInCatchVariables": True,
                "alwaysStrict": True,
                "noUnusedLocals": True,
                "noUnusedParameters": True,
                "noImplicitReturns": True,
                "noFallthroughCasesInSwitch": True,
                "noUncheckedIndexedAccess": True,
                "noImplicitOverride": True,
                "exactOptionalPropertyTypes": True,
            }

            issues = []
            enabled_count = 0
            for rule, expected in strict_rules.items():
                actual = compiler_opts.get(rule)
                if actual != expected:
                    issues.append(f"'{rule}' should be {expected} (current: {actual})")
                else:
                    enabled_count += 1

            return {
                "exists": True,
                "strict_score": f"{enabled_count}/{len(strict_rules)}",
                "strict": compiler_opts.get("strict", False),
                "target": compiler_opts.get("target", "unknown"),
                "module": compiler_opts.get("module", "unknown"),
                "issues": issues[:10]
            }
        except Exception as e:
            return {"exists": True, "error": str(e)}

    def check_eslint(self) -> dict[str, Any]:
        """Vérifie la configuration ESLint."""
        eslint_files = list(self.path.glob("eslint.config.*")) + \
                       list(self.path.glob(".eslintrc*"))

        if not eslint_files:
            return {"configured": False, "issues": ["No ESLint config found"]}

        eslint_file = eslint_files[0]
        content = eslint_file.read_text()

        checks = {
            "typescript_eslint": "@typescript-eslint" in content,
            "strict_config": "strict" in content.lower(),
            "type_checked": "type-checked" in content or "typeChecked" in content,
            "flat_config": eslint_file.name.startswith("eslint.config"),
        }

        issues = []
        if not checks["typescript_eslint"]:
            issues.append("Missing @typescript-eslint plugin")
        if not checks["strict_config"]:
            issues.append("Consider using 'strict' or 'strictTypeChecked' preset")
        if not checks["flat_config"]:
            issues.append("Consider migrating to ESLint 9 flat config")

        return {
            "configured": True,
            "file": eslint_file.name,
            "checks": checks,
            "issues": issues
        }

    def run_eslint(self) -> Dict | None:
        """Exécute ESLint si disponible."""
        try:
            result = subprocess.run(
                ["npx", "eslint", ".", "--format", "json", "--max-warnings", "0"],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.stdout:
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    def audit(self) -> dict[str, Any]:
        """Lance l'audit complet."""
        # Check configs
        self.results["tsconfig_check"] = self.check_tsconfig()
        self.results["eslint_check"] = self.check_eslint()

        # Scan files
        exclude_dirs = {'node_modules', 'dist', 'build', '.next', 'coverage', '__pycache__'}

        for filepath in self.path.rglob('*.ts'):
            if any(excl in filepath.parts for excl in exclude_dirs):
                continue
            if filepath.suffix in ['.d.ts']:  # Skip declaration files
                continue

            issues = self.analyze_file(filepath)
            for issue in issues:
                self.results["issues"][issue["severity"]].append(issue)
            self.results["files_analyzed"] += 1

        for filepath in self.path.rglob('*.tsx'):
            if any(excl in filepath.parts for excl in exclude_dirs):
                continue

            issues = self.analyze_file(filepath)
            for issue in issues:
                self.results["issues"][issue["severity"]].append(issue)
            self.results["files_analyzed"] += 1

        # Generate recommendations
        self._generate_recommendations()

        return self.results

    def _generate_recommendations(self):
        """Génère des recommandations basées sur l'audit."""
        recs = []

        if self.results["summary"]["critical"] > 0:
            recs.append("URGENT: Eliminate all 'any' types and @ts-ignore directives")

        tsconfig = self.results["tsconfig_check"]
        if tsconfig and not tsconfig.get("strict"):
            recs.append("Enable 'strict: true' in tsconfig.json for maximum type safety")

        if tsconfig and tsconfig.get("issues"):
            recs.append("Consider enabling more strict compiler options (see tsconfig issues)")

        eslint = self.results["eslint_check"]
        if eslint and not eslint.get("configured"):
            recs.append("Set up ESLint with @typescript-eslint for code quality enforcement")

        if self.results["summary"]["high"] > 10:
            recs.append("High number of non-null assertions - consider refactoring")

        if not recs:
            recs.append("Code follows TypeScript strict best practices - excellent!")

        self.results["recommendations"] = recs


def print_report(results: dict[str, Any], verbose: bool = False):
    """Affiche le rapport d'audit."""
    print(f"\n{'='*60}")
    print(f" TypeScript Strict Audit Report")
    print(f" Path: {results['path']}")
    print(f"{'='*60}\n")

    # Summary
    s = results["summary"]
    total = sum(s.values())
    print(f" Summary:")
    print(f"   Files analyzed: {results['files_analyzed']}")
    print(f"   Total issues: {total}")
    print(f"   Critical: {s['critical']} | High: {s['high']} | Medium: {s['medium']} | Low: {s['low']}")

    # Score calculation
    if results['files_analyzed'] > 0:
        score = max(0, 100 - (s['critical'] * 10) - (s['high'] * 3) - (s['medium'] * 1))
        print(f"   Strict Score: {score}/100")

    # TSConfig
    ts = results.get("tsconfig_check", {})
    if ts:
        print(f"\n TSConfig:")
        print(f"   Exists: {'Yes' if ts.get('exists') else 'No'}")
        if ts.get("strict_score"):
            print(f"   Strict rules: {ts['strict_score']}")
        if ts.get("issues") and verbose:
            for issue in ts["issues"][:5]:
                print(f"   - {issue}")

    # ESLint
    es = results.get("eslint_check", {})
    if es:
        print(f"\n ESLint:")
        print(f"   Configured: {'Yes' if es.get('configured') else 'No'}")
        if es.get("file"):
            print(f"   Config: {es['file']}")

    # Critical Issues
    if results["issues"].get("critical"):
        print(f"\n Critical Issues (first 10):")
        for issue in results["issues"]["critical"][:10]:
            print(f"   [{issue['file']}:{issue['line']}] {issue['issue']}")
            if verbose:
                print(f"      {issue['code']}")

    # High Issues
    if results["issues"].get("high") and verbose:
        print(f"\n High Severity Issues (first 10):")
        for issue in results["issues"]["high"][:10]:
            print(f"   [{issue['file']}:{issue['line']}] {issue['issue']}")

    # Recommendations
    if results.get("recommendations"):
        print(f"\n Recommendations:")
        for rec in results["recommendations"]:
            print(f"   * {rec}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="AURA TypeScript Strict Auditor")
    parser.add_argument("path", nargs="?", default=".", help="Path to audit")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()
    path = Path(args.path)

    if not path.exists():
        print(f"Path not found: {path}")
        sys.exit(1)

    auditor = TSStrictAuditor(path, verbose=args.verbose)
    results = auditor.audit()

    if args.json:
        print(json.dumps(results, indent=2, default=list))
    else:
        print_report(results, verbose=args.verbose)


if __name__ == "__main__":
    main()
