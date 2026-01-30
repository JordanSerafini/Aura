#!/usr/bin/env python3
"""
AURA-OS Self-Reflection Agent v1.0
Pattern de réflexion inspiré de ReMA, Reflexion, et SCoRe (2025-2026)

Architecture:
- Dual-loop: Extrospection (critique externe) + Introspection (auto-évaluation)
- Mémoire des réflexions pour amélioration continue
- Scoring de confiance calibré

Team: core (meta-cognition)
Sources: arxiv.org/abs/2503.09501 (ReMA), arxiv.org/abs/2409.12917 (SCoRe)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


REFLECTION_DIR = Path.home() / ".aura" / "reflections"
REFLECTION_DIR.mkdir(parents=True, exist_ok=True)


class SelfReflectionAgent:
    """Agent de réflexion basé sur les patterns 2025-2026."""

    REFLECTION_PROMPTS = {
        "task_completion": [
            "Was the task fully completed as requested?",
            "Were there any errors or issues during execution?",
            "What could be done better next time?",
            "Were the right tools/agents used?",
            "Was the response appropriate in tone and length?"
        ],
        "error_analysis": [
            "What was the root cause of the error?",
            "Was this error predictable?",
            "What pattern led to this failure?",
            "How can similar errors be prevented?",
            "Should a fallback have been triggered earlier?"
        ],
        "quality_check": [
            "Does the output meet quality standards?",
            "Is the information accurate and complete?",
            "Were any assumptions made that should be verified?",
            "Is there technical debt introduced?",
            "Would this pass a code review?"
        ]
    }

    CONFIDENCE_LEVELS = {
        "very_high": {"score": 0.95, "desc": "Highly confident, verified result"},
        "high": {"score": 0.80, "desc": "Confident, standard execution"},
        "medium": {"score": 0.60, "desc": "Some uncertainty, might need review"},
        "low": {"score": 0.40, "desc": "Uncertain, recommend human verification"},
        "very_low": {"score": 0.20, "desc": "Likely incorrect, needs intervention"}
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.reflections_file = REFLECTION_DIR / "reflection_log.jsonl"

    def reflect_on_task(
        self,
        task_description: str,
        task_outcome: str,
        success: bool,
        tools_used: list[str] | None = None,
        duration_seconds: float | None = None
    ) -> dict:
        """
        Effectue une réflexion sur une tâche complétée.
        Pattern Reflexion: analyse verbale après exécution.
        """
        reflection = {
            "timestamp": datetime.now().isoformat(),
            "type": "task_completion",
            "task": task_description,
            "outcome": task_outcome,
            "success": success,
            "tools_used": tools_used or [],
            "duration_seconds": duration_seconds,
            "analysis": {
                "what_went_well": [],
                "what_could_improve": [],
                "lessons_learned": [],
                "confidence_assessment": None
            }
        }

        # Analyse automatique basée sur les patterns
        if success:
            reflection["analysis"]["what_went_well"].append(
                "Task completed successfully"
            )
            if duration_seconds and duration_seconds < 5:
                reflection["analysis"]["what_went_well"].append(
                    "Fast execution time"
                )
            reflection["analysis"]["confidence_assessment"] = "high"
        else:
            reflection["analysis"]["what_could_improve"].append(
                "Task did not complete as expected"
            )
            reflection["analysis"]["lessons_learned"].append(
                f"Review error handling for: {task_description[:50]}"
            )
            reflection["analysis"]["confidence_assessment"] = "low"

        # Analyse des outils utilisés
        if tools_used:
            if len(tools_used) > 5:
                reflection["analysis"]["what_could_improve"].append(
                    "Consider consolidating tool usage"
                )
            if "Bash" in tools_used and any(
                agent in str(tools_used) for agent in ["security", "process", "system"]
            ):
                reflection["analysis"]["what_went_well"].append(
                    "Used appropriate AURA agents instead of raw commands"
                )

        # Sauvegarder la réflexion
        self._save_reflection(reflection)

        return reflection

    def reflect_on_error(
        self,
        error_message: str,
        context: str,
        attempted_fix: str | None = None
    ) -> dict:
        """
        Réflexion sur une erreur (pattern SCoRe).
        """
        reflection = {
            "timestamp": datetime.now().isoformat(),
            "type": "error_analysis",
            "error": error_message,
            "context": context,
            "attempted_fix": attempted_fix,
            "analysis": {
                "root_cause_hypothesis": None,
                "prevention_strategy": None,
                "severity": "medium"
            }
        }

        # Classification automatique de l'erreur
        error_lower = error_message.lower()
        if "permission" in error_lower or "access denied" in error_lower:
            reflection["analysis"]["root_cause_hypothesis"] = "Permission issue"
            reflection["analysis"]["prevention_strategy"] = (
                "Check permissions before attempting operation"
            )
        elif "not found" in error_lower or "no such" in error_lower:
            reflection["analysis"]["root_cause_hypothesis"] = "Missing resource"
            reflection["analysis"]["prevention_strategy"] = (
                "Verify resource existence before operation"
            )
        elif "timeout" in error_lower:
            reflection["analysis"]["root_cause_hypothesis"] = "Operation timeout"
            reflection["analysis"]["prevention_strategy"] = (
                "Run long operations in background"
            )
            reflection["analysis"]["severity"] = "low"
        elif "memory" in error_lower or "oom" in error_lower:
            reflection["analysis"]["root_cause_hypothesis"] = "Resource exhaustion"
            reflection["analysis"]["prevention_strategy"] = (
                "Monitor resources, use chunking for large operations"
            )
            reflection["analysis"]["severity"] = "high"

        self._save_reflection(reflection)
        return reflection

    def meta_reflect(self, recent_count: int = 10) -> dict:
        """
        Meta-réflexion: analyse des patterns dans les réflexions récentes.
        Pattern ReMA: meta-thinking sur le niveau supérieur.
        """
        reflections = self._load_recent_reflections(recent_count)

        meta_analysis = {
            "timestamp": datetime.now().isoformat(),
            "type": "meta_reflection",
            "analyzed_count": len(reflections),
            "patterns": {
                "success_rate": 0,
                "common_issues": [],
                "improvement_trends": [],
                "recommendations": []
            }
        }

        if not reflections:
            meta_analysis["patterns"]["recommendations"].append(
                "No recent reflections to analyze"
            )
            return meta_analysis

        # Calcul du taux de succès
        task_reflections = [
            r for r in reflections if r.get("type") == "task_completion"
        ]
        if task_reflections:
            successes = sum(1 for r in task_reflections if r.get("success"))
            meta_analysis["patterns"]["success_rate"] = round(
                successes / len(task_reflections) * 100, 1
            )

        # Identification des erreurs récurrentes
        error_reflections = [
            r for r in reflections if r.get("type") == "error_analysis"
        ]
        if error_reflections:
            causes = [
                r.get("analysis", {}).get("root_cause_hypothesis")
                for r in error_reflections
                if r.get("analysis", {}).get("root_cause_hypothesis")
            ]
            # Compter les occurrences
            cause_counts: dict[str, int] = {}
            for cause in causes:
                cause_counts[cause] = cause_counts.get(cause, 0) + 1

            meta_analysis["patterns"]["common_issues"] = [
                {"issue": k, "count": v}
                for k, v in sorted(cause_counts.items(), key=lambda x: -x[1])[:5]
            ]

        # Générer des recommandations
        success_rate = meta_analysis["patterns"]["success_rate"]
        if success_rate < 70:
            meta_analysis["patterns"]["recommendations"].append(
                "Success rate below 70% - review task planning"
            )
        if len(error_reflections) > len(task_reflections) * 0.3:
            meta_analysis["patterns"]["recommendations"].append(
                "High error rate - consider adding more validation steps"
            )

        self._save_reflection(meta_analysis)
        return meta_analysis

    def assess_confidence(
        self,
        task_type: str,
        has_verification: bool = False,
        complexity: str = "medium"
    ) -> dict:
        """
        Évalue le niveau de confiance pour une tâche.
        Basé sur les recherches de calibration (ICLR 2025).
        """
        base_confidence = 0.7

        # Ajustements basés sur les facteurs
        if has_verification:
            base_confidence += 0.15
        if complexity == "low":
            base_confidence += 0.1
        elif complexity == "high":
            base_confidence -= 0.15

        # Mapper au niveau de confiance
        if base_confidence >= 0.9:
            level = "very_high"
        elif base_confidence >= 0.75:
            level = "high"
        elif base_confidence >= 0.55:
            level = "medium"
        elif base_confidence >= 0.35:
            level = "low"
        else:
            level = "very_low"

        return {
            "score": round(base_confidence, 2),
            "level": level,
            "description": self.CONFIDENCE_LEVELS[level]["desc"],
            "factors": {
                "task_type": task_type,
                "has_verification": has_verification,
                "complexity": complexity
            }
        }

    def _save_reflection(self, reflection: dict) -> None:
        """Sauvegarde une réflexion dans le log."""
        with open(self.reflections_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(reflection, ensure_ascii=False) + "\n")

    def _load_recent_reflections(self, count: int) -> list[dict]:
        """Charge les réflexions récentes."""
        if not self.reflections_file.exists():
            return []

        reflections = []
        with open(self.reflections_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        reflections.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return reflections[-count:]

    def get_stats(self) -> dict:
        """Retourne les statistiques des réflexions."""
        reflections = self._load_recent_reflections(1000)

        stats = {
            "total_reflections": len(reflections),
            "by_type": {},
            "success_rate": None,
            "avg_confidence": None
        }

        for r in reflections:
            rtype = r.get("type", "unknown")
            stats["by_type"][rtype] = stats["by_type"].get(rtype, 0) + 1

        task_refs = [r for r in reflections if r.get("type") == "task_completion"]
        if task_refs:
            successes = sum(1 for r in task_refs if r.get("success"))
            stats["success_rate"] = round(successes / len(task_refs) * 100, 1)

        return stats


def print_report(result: dict, verbose: bool = False) -> None:
    """Affiche un rapport de réflexion."""
    print(f"\n{'='*60}")
    print(f" Self-Reflection Report")
    print(f" Type: {result.get('type', 'unknown')}")
    print(f"{'='*60}\n")

    if result.get("type") == "task_completion":
        print(f" Task: {result.get('task', 'N/A')[:60]}")
        print(f" Success: {'Yes' if result.get('success') else 'No'}")
        analysis = result.get("analysis", {})
        print(f" Confidence: {analysis.get('confidence_assessment', 'N/A')}")

        if analysis.get("what_went_well"):
            print("\n What went well:")
            for item in analysis["what_went_well"]:
                print(f"   + {item}")

        if analysis.get("what_could_improve"):
            print("\n What could improve:")
            for item in analysis["what_could_improve"]:
                print(f"   - {item}")

    elif result.get("type") == "error_analysis":
        print(f" Error: {result.get('error', 'N/A')[:60]}")
        analysis = result.get("analysis", {})
        print(f" Root cause: {analysis.get('root_cause_hypothesis', 'Unknown')}")
        print(f" Prevention: {analysis.get('prevention_strategy', 'N/A')}")

    elif result.get("type") == "meta_reflection":
        patterns = result.get("patterns", {})
        print(f" Analyzed: {result.get('analyzed_count', 0)} reflections")
        print(f" Success rate: {patterns.get('success_rate', 'N/A')}%")

        if patterns.get("common_issues"):
            print("\n Common issues:")
            for issue in patterns["common_issues"][:5]:
                print(f"   - {issue['issue']}: {issue['count']}x")

        if patterns.get("recommendations"):
            print("\n Recommendations:")
            for rec in patterns["recommendations"]:
                print(f"   * {rec}")

    elif "stats" in str(result.get("type", "")):
        print(f" Total reflections: {result.get('total_reflections', 0)}")
        print(f" Success rate: {result.get('success_rate', 'N/A')}%")
        if result.get("by_type"):
            print("\n By type:")
            for t, c in result["by_type"].items():
                print(f"   - {t}: {c}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="AURA Self-Reflection Agent")
    parser.add_argument(
        "action",
        choices=["task", "error", "meta", "confidence", "stats"],
        help="Action to perform"
    )
    parser.add_argument("--task", help="Task description")
    parser.add_argument("--outcome", help="Task outcome")
    parser.add_argument("--success", action="store_true", help="Task succeeded")
    parser.add_argument("--error", help="Error message")
    parser.add_argument("--context", help="Error context")
    parser.add_argument("--count", type=int, default=10, help="Count for meta")
    parser.add_argument("--type", help="Task type for confidence")
    parser.add_argument("--complexity", default="medium", help="Complexity level")
    parser.add_argument("--verified", action="store_true", help="Has verification")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    agent = SelfReflectionAgent(verbose=args.verbose)

    result = {}

    if args.action == "task":
        if not args.task or not args.outcome:
            print("Error: --task and --outcome required for task reflection")
            sys.exit(1)
        result = agent.reflect_on_task(
            task_description=args.task,
            task_outcome=args.outcome,
            success=args.success
        )

    elif args.action == "error":
        if not args.error:
            print("Error: --error required for error reflection")
            sys.exit(1)
        result = agent.reflect_on_error(
            error_message=args.error,
            context=args.context or ""
        )

    elif args.action == "meta":
        result = agent.meta_reflect(recent_count=args.count)

    elif args.action == "confidence":
        result = agent.assess_confidence(
            task_type=args.type or "general",
            has_verification=args.verified,
            complexity=args.complexity
        )

    elif args.action == "stats":
        result = agent.get_stats()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result, verbose=args.verbose)


if __name__ == "__main__":
    main()
