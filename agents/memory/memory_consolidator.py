#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Memory Consolidator - Agent de consolidation mémoire.
Analyse les épisodes, extrait des patterns, génère des skills, et enrichit le graphe.
Inspiré de Nemori et du pattern de consolidation Episodic → Semantic/Procedural.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from memory_types import (
    Episode, Skill, KnowledgeTriple, ConsolidationResult,
    MemoryMetadata, MemoryStatus, MEMORY_CONFIG
)
from episodic_memory import EpisodicMemory
from procedural_memory import ProceduralMemory
from knowledge_graph import KnowledgeGraph


class MemoryConsolidator:
    """
    Agent de consolidation mémoire.
    Transforme les épisodes en skills et connaissances durables.
    """

    def __init__(
        self,
        episodic: EpisodicMemory | None = None,
        procedural: ProceduralMemory | None = None,
        knowledge: KnowledgeGraph | None = None
    ):
        """Initialise le consolidateur avec les composants mémoire."""
        self.episodic = episodic or EpisodicMemory()
        self.procedural = procedural or ProceduralMemory()
        self.knowledge = knowledge or KnowledgeGraph()

        # Logs de consolidation
        self.logs_dir = Path.home() / ".aura" / "memory" / "consolidation_logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def consolidate(
        self,
        min_episodes: int = None,
        min_valence: float = 0.3,
        dry_run: bool = False
    ) -> ConsolidationResult:
        """
        Lance une consolidation complète.

        Args:
            min_episodes: Nombre minimum d'épisodes pour consolider (défaut: config)
            min_valence: Valence minimum pour considérer un épisode réussi
            dry_run: Simuler sans appliquer les changements

        Returns:
            Résultat de la consolidation
        """
        min_episodes = min_episodes or MEMORY_CONFIG["consolidation_threshold"]

        result = ConsolidationResult(
            episodes_processed=0,
            skills_created=0,
            skills_updated=0,
            triples_extracted=0,
            episodes_archived=0
        )

        # 1. Récupérer les épisodes réussis non consolidés
        successful_episodes = self.episodic.get_successful_episodes(
            min_valence=min_valence,
            limit=100
        )

        if len(successful_episodes) < min_episodes:
            result.details["message"] = f"Pas assez d'épisodes ({len(successful_episodes)} < {min_episodes})"
            return result

        result.episodes_processed = len(successful_episodes)

        # 2. Grouper par patterns similaires
        pattern_groups = self._group_by_pattern(successful_episodes)
        result.details["pattern_groups"] = len(pattern_groups)

        # 3. Pour chaque groupe avec assez d'occurrences, créer ou mettre à jour un skill
        for pattern_key, episodes in pattern_groups.items():
            if len(episodes) < MEMORY_CONFIG["min_skill_occurrences"]:
                continue

            skill_result = self._consolidate_pattern_to_skill(
                pattern_key, episodes, dry_run
            )

            if skill_result["created"]:
                result.skills_created += 1
            elif skill_result["updated"]:
                result.skills_updated += 1

            # Marquer les épisodes comme consolidés
            if not dry_run and skill_result.get("skill_id"):
                self.episodic.mark_consolidated(
                    [ep.id for ep in episodes],
                    skill_result["skill_id"]
                )

        # 4. Extraire des triplets de connaissances depuis les épisodes
        for episode in successful_episodes:
            triples_created = self._extract_knowledge_from_episode(episode, dry_run)
            result.triples_extracted += triples_created

        # 5. Archiver les vieux épisodes consolidés
        if not dry_run:
            archived = self._archive_old_consolidated()
            result.episodes_archived = archived

        # Log du résultat
        self._log_consolidation(result)

        return result

    def _group_by_pattern(self, episodes: list[Episode]) -> dict[str, list[Episode]]:
        """
        Groupe les épisodes par patterns d'action similaires.
        Utilise une heuristique simple basée sur les premiers mots de l'action.
        """
        groups = defaultdict(list)

        for episode in episodes:
            # Extraire un pattern simplifié
            action_words = episode.action.lower().split()[:3]
            pattern_key = "_".join(action_words) if action_words else "unknown"

            groups[pattern_key].append(episode)

        return dict(groups)

    def _consolidate_pattern_to_skill(
        self,
        pattern_key: str,
        episodes: list[Episode],
        dry_run: bool
    ) -> dict[str, Any]:
        """
        Consolide un groupe d'épisodes en skill.
        """
        result = {"created": False, "updated": False, "skill_id": None}

        # Calculer les statistiques du groupe
        avg_valence = sum(ep.emotional_valence for ep in episodes) / len(episodes)
        avg_importance = sum(ep.importance for ep in episodes) / len(episodes)

        # Extraire le pattern commun
        contexts = [ep.context for ep in episodes]
        actions = [ep.action for ep in episodes]
        outcomes = [ep.outcome for ep in episodes]

        # Générer les composants du skill
        skill_name = f"skill_{pattern_key}"
        description = f"Pattern appris depuis {len(episodes)} épisodes réussis"

        # Pattern = action commune généralisée
        common_action = self._find_common_pattern(actions)

        # Conditions = contextes communs
        trigger_conditions = self._extract_trigger_conditions(contexts)

        # Template d'action = action avec placeholders
        action_template = self._generalize_action(common_action)

        # Vérifier si un skill similaire existe
        existing_skill = self.procedural.get_skill_by_name(skill_name)

        if dry_run:
            if existing_skill:
                result["updated"] = True
                result["skill_id"] = existing_skill.id
            else:
                result["created"] = True
            return result

        if existing_skill:
            # Mettre à jour le skill existant
            self.procedural.update_skill(
                existing_skill.id,
                pattern=common_action,
                trigger_conditions=trigger_conditions,
                action_template=action_template
            )
            # Ajouter les nouveaux épisodes sources
            for ep in episodes:
                self.procedural.add_source_episode(existing_skill.id, ep.id)

            result["updated"] = True
            result["skill_id"] = existing_skill.id
        else:
            # Créer un nouveau skill
            skill_id = self.procedural.create_skill(
                name=skill_name,
                description=description,
                pattern=common_action,
                trigger_conditions=trigger_conditions,
                action_template=action_template,
                source_episodes=[ep.id for ep in episodes],
                success_rate=avg_valence
            )
            result["created"] = True
            result["skill_id"] = skill_id

        return result

    def _find_common_pattern(self, texts: list[str]) -> str:
        """Trouve le pattern commun dans une liste de textes."""
        if not texts:
            return ""

        # Tokenizer simple
        word_sets = [set(t.lower().split()) for t in texts]

        # Intersection des mots
        common_words = word_sets[0]
        for ws in word_sets[1:]:
            common_words &= ws

        # Prendre le premier texte et garder seulement les mots communs
        first_words = texts[0].split()
        pattern = " ".join(w for w in first_words if w.lower() in common_words)

        return pattern if pattern else texts[0][:100]

    def _extract_trigger_conditions(self, contexts: list[str]) -> list[str]:
        """Extrait les conditions déclencheuses depuis les contextes."""
        # Mots-clés fréquents dans les contextes
        word_freq = defaultdict(int)
        for ctx in contexts:
            for word in ctx.lower().split():
                if len(word) > 3:  # Ignorer les petits mots
                    word_freq[word] += 1

        # Garder les mots présents dans au moins la moitié des contextes
        threshold = len(contexts) / 2
        common_keywords = [w for w, c in word_freq.items() if c >= threshold]

        return common_keywords[:5]  # Max 5 conditions

    def _generalize_action(self, action: str) -> str:
        """Généralise une action en template avec placeholders."""
        # Remplacer les valeurs spécifiques par des placeholders
        import re

        template = action

        # Remplacer les chemins
        template = re.sub(r'/[\w/.-]+', '{{PATH}}', template)

        # Remplacer les nombres
        template = re.sub(r'\b\d+\b', '{{NUMBER}}', template)

        # Remplacer les chaînes entre guillemets
        template = re.sub(r'"[^"]*"', '{{STRING}}', template)
        template = re.sub(r"'[^']*'", '{{STRING}}', template)

        return template

    def _extract_knowledge_from_episode(
        self,
        episode: Episode,
        dry_run: bool
    ) -> int:
        """Extrait des triplets de connaissance depuis un épisode."""
        if dry_run:
            return 0

        created_count = 0

        # Combiner contexte et action pour l'extraction
        text = f"{episode.context}. {episode.action}. {episode.outcome}"

        # Utiliser l'extraction automatique du graphe
        created_ids = self.knowledge.extract_triples_from_text(
            text,
            source_episode=episode.id
        )
        created_count = len(created_ids)

        # Ajouter des triplets explicites pour les entités mentionnées
        if episode.entities:
            for entity in episode.entities:
                self.knowledge.add_triple(
                    subject=entity,
                    predicate="mentioned_in",
                    obj=f"episode_{episode.id[:8]}",
                    confidence=0.9,
                    source_episode=episode.id
                )
                created_count += 1

        return created_count

    def _archive_old_consolidated(self, days_old: int = 30) -> int:
        """Archive les épisodes consolidés plus anciens que X jours."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days_old)
        cutoff_iso = cutoff.isoformat()

        archived = 0
        for episode in self.episodic.get_recent_episodes(limit=1000):
            if episode.metadata.status == MemoryStatus.CONSOLIDATED.name:
                if episode.timestamp < cutoff_iso:
                    if self.episodic.archive_episode(episode.id):
                        archived += 1

        return archived

    def _log_consolidation(self, result: ConsolidationResult):
        """Enregistre le résultat de consolidation dans un log."""
        log_file = self.logs_dir / f"consolidation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        log_data = {
            "timestamp": result.timestamp,
            "episodes_processed": result.episodes_processed,
            "skills_created": result.skills_created,
            "skills_updated": result.skills_updated,
            "triples_extracted": result.triples_extracted,
            "episodes_archived": result.episodes_archived,
            "details": result.details
        }
        log_file.write_text(json.dumps(log_data, indent=2))

    def analyze_patterns(self, limit: int = 50) -> dict[str, Any]:
        """
        Analyse les patterns dans les épisodes récents.
        Utile pour voir quels skills pourraient être créés.
        """
        episodes = self.episodic.get_recent_episodes(limit=limit)
        successful = [ep for ep in episodes if ep.emotional_valence >= 0.3]

        pattern_groups = self._group_by_pattern(successful)

        analysis = {
            "total_episodes": len(episodes),
            "successful_episodes": len(successful),
            "pattern_groups": {},
            "potential_skills": []
        }

        for pattern_key, group in pattern_groups.items():
            group_info = {
                "count": len(group),
                "avg_valence": sum(ep.emotional_valence for ep in group) / len(group),
                "sample_action": group[0].action[:100] if group else ""
            }
            analysis["pattern_groups"][pattern_key] = group_info

            if len(group) >= MEMORY_CONFIG["min_skill_occurrences"]:
                analysis["potential_skills"].append({
                    "name": f"skill_{pattern_key}",
                    "episodes": len(group),
                    "confidence": group_info["avg_valence"]
                })

        return analysis

    def get_consolidation_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Récupère l'historique des consolidations."""
        log_files = sorted(self.logs_dir.glob("consolidation_*.json"), reverse=True)
        history = []

        for log_file in log_files[:limit]:
            try:
                data = json.loads(log_file.read_text())
                history.append(data)
            except Exception:
                pass

        return history

    def get_stats(self) -> dict[str, Any]:
        """Statistiques globales du système de mémoire."""
        return {
            "episodic": self.episodic.get_stats(),
            "procedural": self.procedural.get_stats(),
            "knowledge": self.knowledge.get_stats(),
            "consolidation_logs": len(list(self.logs_dir.glob("consolidation_*.json")))
        }


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aura Memory Consolidator")
    subparsers = parser.add_subparsers(dest="command")

    # consolidate
    cons_p = subparsers.add_parser("consolidate", help="Lancer une consolidation")
    cons_p.add_argument("--min-episodes", type=int, default=None)
    cons_p.add_argument("--min-valence", type=float, default=0.3)
    cons_p.add_argument("--dry-run", action="store_true")

    # analyze
    analyze_p = subparsers.add_parser("analyze", help="Analyser les patterns")
    analyze_p.add_argument("--limit", type=int, default=50)

    # history
    hist_p = subparsers.add_parser("history", help="Historique des consolidations")
    hist_p.add_argument("--limit", type=int, default=10)

    # stats
    subparsers.add_parser("stats", help="Statistiques globales")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    consolidator = MemoryConsolidator()

    if args.command == "consolidate":
        print("Lancement de la consolidation...")
        result = consolidator.consolidate(
            min_episodes=args.min_episodes,
            min_valence=args.min_valence,
            dry_run=args.dry_run
        )

        print("\n=== Résultat de la consolidation ===")
        print(f"  Épisodes traités: {result.episodes_processed}")
        print(f"  Skills créés: {result.skills_created}")
        print(f"  Skills mis à jour: {result.skills_updated}")
        print(f"  Triplets extraits: {result.triples_extracted}")
        print(f"  Épisodes archivés: {result.episodes_archived}")
        if args.dry_run:
            print("\n  (Mode dry-run - aucun changement appliqué)")
        if result.details:
            print(f"\n  Détails: {result.details}")

    elif args.command == "analyze":
        analysis = consolidator.analyze_patterns(limit=args.limit)

        print("=== Analyse des patterns ===")
        print(f"Épisodes analysés: {analysis['total_episodes']}")
        print(f"Épisodes réussis: {analysis['successful_episodes']}")
        print(f"\nGroupes de patterns: {len(analysis['pattern_groups'])}")

        for pattern, info in analysis["pattern_groups"].items():
            print(f"\n  [{pattern}]")
            print(f"    Count: {info['count']} | Avg valence: {info['avg_valence']:.2f}")
            print(f"    Sample: {info['sample_action'][:60]}...")

        if analysis["potential_skills"]:
            print(f"\n=== Skills potentiels ({len(analysis['potential_skills'])}) ===")
            for skill in analysis["potential_skills"]:
                print(f"  - {skill['name']} ({skill['episodes']} épisodes, conf: {skill['confidence']:.2f})")

    elif args.command == "history":
        history = consolidator.get_consolidation_history(limit=args.limit)

        if not history:
            print("Aucun historique de consolidation.")
        else:
            print(f"=== Historique ({len(history)} consolidations) ===\n")
            for entry in history:
                print(f"[{entry['timestamp']}]")
                print(f"  Épisodes: {entry['episodes_processed']}")
                print(f"  Skills: +{entry['skills_created']} / ↻{entry['skills_updated']}")
                print(f"  Triplets: +{entry['triples_extracted']}")
                print()

    elif args.command == "stats":
        stats = consolidator.get_stats()

        print("=== Statistiques du système de mémoire ===\n")

        print("Mémoire Épisodique:")
        for k, v in stats["episodic"].items():
            print(f"  {k}: {v}")

        print("\nMémoire Procédurale:")
        for k, v in stats["procedural"].items():
            print(f"  {k}: {v}")

        print("\nGraphe de Connaissances:")
        for k, v in stats["knowledge"].items():
            print(f"  {k}: {v}")

        print(f"\nLogs de consolidation: {stats['consolidation_logs']}")
