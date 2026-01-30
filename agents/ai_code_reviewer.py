#!/usr/bin/env python3
"""
AURA-OS AI Code Reviewer Agent
Review automatique de code inspiré CodeRabbit/GitHub Copilot patterns 2026
Team: core (dev workflows)
Sources: coderabbitai/ai-pr-reviewer, GitHub AI code reviews, Anthropic patterns
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
import difflib


class AICodeReviewer:
    """Review de code automatique avec patterns AI 2026."""

    # Catégories de review (inspiré CodeRabbit)
    REVIEW_CATEGORIES = {
        "security": {
            "weight": 10,
            "patterns": [
                (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password detected", "CRITICAL"),
                (r'api_key\s*=\s*["\'][^"\']+["\']', "Hardcoded API key detected", "CRITICAL"),
                (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret detected", "CRITICAL"),
                (r'eval\s*\(', "eval() is dangerous - code injection risk", "HIGH"),
                (r'exec\s*\(', "exec() allows arbitrary code execution", "HIGH"),
                (r'innerHTML\s*=', "innerHTML can cause XSS vulnerabilities", "HIGH"),
                (r'dangerouslySetInnerHTML', "React dangerous HTML injection", "MEDIUM"),
                (r'\.query\s*\([^)]*\+', "Possible SQL injection - use parameterized queries", "HIGH"),
                (r'subprocess\..*shell\s*=\s*True', "Shell=True is dangerous", "HIGH"),
                (r'pickle\.load', "Pickle deserialization is unsafe for untrusted data", "MEDIUM"),
            ]
        },
        "bugs": {
            "weight": 8,
            "patterns": [
                (r'==\s*None|None\s*==', "Use 'is None' instead of '== None'", "MEDIUM"),
                (r'!=\s*None|None\s*!=', "Use 'is not None' instead of '!= None'", "MEDIUM"),
                (r'except\s*:', "Bare except catches all exceptions including KeyboardInterrupt", "HIGH"),
                (r'\.then\s*\([^)]*\)(?!.*\.catch)', "Promise without error handling", "MEDIUM"),
                (r'async\s+function.*\{[^}]*await[^}]*\}(?!.*try)', "Async without try-catch", "LOW"),
                (r'return\s+await\s+', "Unnecessary 'return await' - just return the promise", "LOW"),
                (r'if\s*\([^)]+\)\s*;', "Empty if statement - likely a bug", "HIGH"),
                (r'=\s*=\s*=', "Triple equals typo?", "HIGH"),
            ]
        },
        "performance": {
            "weight": 5,
            "patterns": [
                (r'for\s+\w+\s+in\s+range\s*\(\s*len\s*\(', "Use enumerate() instead of range(len())", "LOW"),
                (r'\.append\([^)]+\)\s*$', "Consider list comprehension for better performance", "INFO"),
                (r'SELECT\s+\*', "SELECT * - specify columns for better performance", "MEDIUM"),
                (r'N\+1', "Potential N+1 query detected", "HIGH"),
                (r'useEffect\s*\(\s*\(\)\s*=>\s*\{[^}]*\},\s*\[\s*\]\s*\)', "Empty deps array - runs only once", "INFO"),
                (r'JSON\.parse\s*\(.*JSON\.stringify', "Unnecessary JSON round-trip", "MEDIUM"),
                (r'\.filter\([^)]+\)\.map\(', "Consider using reduce() for single pass", "LOW"),
            ]
        },
        "maintainability": {
            "weight": 3,
            "patterns": [
                (r'TODO|FIXME|HACK|XXX', "Technical debt marker", "INFO"),
                (r'magic\s*number|[^\w](?:86400|3600|60000|1000)[^\d]', "Magic number - use named constant", "LOW"),
                (r'function\s+\w+\s*\([^)]{100,}\)', "Too many function parameters (>5)", "MEDIUM"),
                (r'(?:if|else|for|while)[^{]*\n[^{]*\n[^{]*\n[^{]*\n[^{]*\n', "Deep nesting - consider early return", "MEDIUM"),
                (r'console\.log|print\s*\(', "Debug statement in code", "LOW"),
                (r'#.*disabled|//.*disabled', "Disabled code should be removed", "LOW"),
            ]
        },
        "style": {
            "weight": 1,
            "patterns": [
                (r'[^\s]==[^\s]|[^\s]!=[^\s]', "Add spaces around comparison operators", "INFO"),
                (r'\t', "Tabs detected - use spaces for consistency", "INFO"),
                (r'^\s{1,3}[^\s]|^\s{5,7}[^\s]', "Inconsistent indentation", "INFO"),
            ]
        }
    }

    def __init__(self, path: Path, verbose: bool = False):
        self.path = path.resolve()
        self.verbose = verbose
        self.results: dict[str, Any] = {
            "path": str(self.path),
            "reviewed_at": datetime.now().isoformat(),
            "files_reviewed": 0,
            "findings": defaultdict(list),
            "summary": {
                "CRITICAL": 0,
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0,
                "INFO": 0
            },
            "category_scores": {},
            "overall_score": 100,
            "ai_suggestions": []
        }

    def review_file(self, filepath: Path) -> list[Dict]:
        """Review un fichier."""
        findings = []

        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            rel_path = str(filepath.relative_to(self.path))

            for category, config in self.REVIEW_CATEGORIES.items():
                for pattern, message, severity in config["patterns"]:
                    for i, line in enumerate(lines, 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            finding = {
                                "file": rel_path,
                                "line": i,
                                "category": category,
                                "severity": severity,
                                "message": message,
                                "code": line.strip()[:100]
                            }
                            findings.append(finding)
                            self.results["summary"][severity] += 1

        except Exception as e:
            if self.verbose:
                print(f"Error reviewing {filepath}: {e}")

        return findings

    def review_diff(self, diff_content: str) -> list[Dict]:
        """Review un diff (pour intégration PR)."""
        findings = []
        current_file = None
        current_line = 0

        for line in diff_content.split('\n'):
            if line.startswith('+++'):
                current_file = line[4:].strip()
                if current_file.startswith('b/'):
                    current_file = current_file[2:]
            elif line.startswith('@@'):
                # Parse line number from @@ -x,y +a,b @@
                match = re.search(r'\+(\d+)', line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith('+') and not line.startswith('+++'):
                # This is an added line
                added_line = line[1:]

                for category, config in self.REVIEW_CATEGORIES.items():
                    for pattern, message, severity in config["patterns"]:
                        if re.search(pattern, added_line, re.IGNORECASE):
                            findings.append({
                                "file": current_file,
                                "line": current_line,
                                "category": category,
                                "severity": severity,
                                "message": message,
                                "code": added_line.strip()[:100],
                                "is_new_code": True
                            })
                            self.results["summary"][severity] += 1

                current_line += 1
            elif not line.startswith('-'):
                current_line += 1

        return findings

    def get_git_diff(self, base_branch: str = "main") -> str | None:
        """Récupère le diff Git par rapport à une branche."""
        try:
            result = subprocess.run(
                ["git", "diff", base_branch, "--", "*.py", "*.ts", "*.tsx", "*.js", "*.jsx"],
                cwd=self.path,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout if result.returncode == 0 else None
        except Exception:
            return None

    def calculate_scores(self):
        """Calcule les scores par catégorie."""
        for category, config in self.REVIEW_CATEGORIES.items():
            category_findings = [f for f in sum(self.results["findings"].values(), [])
                               if f.get("category") == category]

            deductions = sum(
                config["weight"] * {"CRITICAL": 10, "HIGH": 5, "MEDIUM": 2, "LOW": 1, "INFO": 0}.get(f["severity"], 0)
                for f in category_findings
            )

            score = max(0, 100 - deductions)
            self.results["category_scores"][category] = score

        # Overall score
        if self.results["category_scores"]:
            weights = {cat: config["weight"] for cat, config in self.REVIEW_CATEGORIES.items()}
            total_weight = sum(weights.values())
            self.results["overall_score"] = round(
                sum(score * weights[cat] for cat, score in self.results["category_scores"].items()) / total_weight
            )

    def generate_ai_suggestions(self):
        """Génère des suggestions style AI."""
        suggestions = []

        # Security
        if self.results["summary"]["CRITICAL"] > 0:
            suggestions.append({
                "priority": "URGENT",
                "title": "Critical Security Issues Detected",
                "description": "Hardcoded secrets or dangerous functions found. These must be fixed before merge.",
                "action": "Remove hardcoded credentials, use environment variables or secret management."
            })

        # Bugs
        high_bugs = [f for f in self.results["findings"].get("bugs", []) if f["severity"] == "HIGH"]
        if high_bugs:
            suggestions.append({
                "priority": "HIGH",
                "title": "Potential Bugs Detected",
                "description": f"{len(high_bugs)} high-severity potential bugs found.",
                "action": "Review exception handling and null checks."
            })

        # Performance
        perf_issues = self.results["findings"].get("performance", [])
        if len(perf_issues) > 5:
            suggestions.append({
                "priority": "MEDIUM",
                "title": "Performance Improvements Available",
                "description": f"{len(perf_issues)} performance patterns could be optimized.",
                "action": "Consider refactoring loops and database queries."
            })

        # Maintainability
        todos = [f for f in self.results["findings"].get("maintainability", [])
                if "TODO" in f.get("message", "") or "FIXME" in f.get("message", "")]
        if len(todos) > 10:
            suggestions.append({
                "priority": "LOW",
                "title": "Technical Debt Accumulation",
                "description": f"{len(todos)} TODO/FIXME markers found.",
                "action": "Schedule time to address technical debt."
            })

        self.results["ai_suggestions"] = suggestions

    def review(self, diff_only: bool = False, base_branch: str = "main") -> dict[str, Any]:
        """Lance la review complète."""

        if diff_only:
            diff = self.get_git_diff(base_branch)
            if diff:
                findings = self.review_diff(diff)
                for f in findings:
                    self.results["findings"][f["category"]].append(f)
                self.results["mode"] = "diff"
            else:
                self.results["error"] = "Could not get git diff"
                return self.results
        else:
            # Full scan
            exclude_dirs = {'node_modules', 'venv', '.venv', '__pycache__', 'dist',
                          'build', '.git', 'coverage', '.next'}
            extensions = {'.py', '.ts', '.tsx', '.js', '.jsx'}

            for filepath in self.path.rglob('*'):
                if filepath.suffix not in extensions:
                    continue
                if any(excl in filepath.parts for excl in exclude_dirs):
                    continue
                if not filepath.is_file():
                    continue

                findings = self.review_file(filepath)
                for f in findings:
                    self.results["findings"][f["category"]].append(f)
                self.results["files_reviewed"] += 1

            self.results["mode"] = "full"

        self.calculate_scores()
        self.generate_ai_suggestions()

        return self.results


def print_report(results: dict[str, Any], verbose: bool = False):
    """Affiche le rapport de review."""
    print(f"\n{'='*60}")
    print(f" AI Code Review Report")
    print(f" Path: {results['path']}")
    print(f" Mode: {results.get('mode', 'unknown')}")
    print(f"{'='*60}\n")

    # Overall Score
    score = results["overall_score"]
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
    print(f" Overall Score: {score}/100 (Grade: {grade})")

    # Summary
    s = results["summary"]
    print(f"\n Findings Summary:")
    print(f"   CRITICAL: {s['CRITICAL']} | HIGH: {s['HIGH']} | MEDIUM: {s['MEDIUM']} | LOW: {s['LOW']} | INFO: {s['INFO']}")

    if results.get("files_reviewed"):
        print(f"   Files reviewed: {results['files_reviewed']}")

    # Category Scores
    if results.get("category_scores"):
        print(f"\n Category Scores:")
        for cat, score in sorted(results["category_scores"].items(), key=lambda x: x[1]):
            bar = "#" * (score // 10) + "-" * (10 - score // 10)
            print(f"   {cat:15} [{bar}] {score}/100")

    # Critical/High Findings
    all_findings = []
    for findings in results["findings"].values():
        all_findings.extend(findings)

    critical_high = [f for f in all_findings if f["severity"] in ["CRITICAL", "HIGH"]]
    if critical_high:
        print(f"\n Critical/High Severity Issues:")
        for f in critical_high[:15]:
            icon = "[!]" if f["severity"] == "CRITICAL" else "[X]"
            print(f"   {icon} [{f['file']}:{f['line']}] {f['message']}")
            if verbose:
                print(f"       {f['code']}")

    # AI Suggestions
    if results.get("ai_suggestions"):
        print(f"\n AI Suggestions:")
        for sug in results["ai_suggestions"]:
            print(f"   [{sug['priority']}] {sug['title']}")
            print(f"       {sug['description']}")
            print(f"       Action: {sug['action']}")

    # Verdict
    print(f"\n Verdict:")
    if s["CRITICAL"] > 0:
        print("   BLOCK MERGE - Critical security issues must be fixed")
    elif s["HIGH"] > 5:
        print("   REQUEST CHANGES - Multiple high-severity issues need attention")
    elif score < 70:
        print("   REQUEST CHANGES - Code quality below acceptable threshold")
    elif score < 85:
        print("   APPROVE WITH COMMENTS - Minor improvements suggested")
    else:
        print("   APPROVE - Code meets quality standards")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="AURA AI Code Reviewer")
    parser.add_argument("path", nargs="?", default=".", help="Path to review")
    parser.add_argument("--diff", action="store_true", help="Review only git diff")
    parser.add_argument("--base", default="main", help="Base branch for diff (default: main)")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    path = Path(args.path)

    if not path.exists():
        print(f"Path not found: {path}")
        sys.exit(1)

    reviewer = AICodeReviewer(path, verbose=args.verbose)
    results = reviewer.review(diff_only=args.diff, base_branch=args.base)

    if args.json:
        print(json.dumps(results, indent=2, default=list))
    else:
        print_report(results, verbose=args.verbose)

    # Exit code based on findings
    if results["summary"]["CRITICAL"] > 0:
        sys.exit(2)
    elif results["summary"]["HIGH"] > 5:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
