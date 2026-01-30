#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Procedural Memory - Mémoire procédurale pour skills et patterns appris.
Stocke les patterns d'action réussis consolidés depuis la mémoire épisodique.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).parent))
from memory_types import (
    Skill, MemoryMetadata, MemoryScore, MemoryStatus,
    MEMORY_CONFIG, calculate_recency_score
)


class ProceduralMemory:
    """
    Gestionnaire de mémoire procédurale.
    Stocke les skills/patterns appris et leurs conditions d'application.
    """

    COLLECTION_NAME = "skills"

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialise la mémoire procédurale."""
        self.storage_path = storage_path or Path.home() / ".aura" / "memory" / "procedural"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # ChromaDB
        self.client = chromadb.PersistentClient(
            path=str(self.storage_path / "chroma_db"),
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Mémoire procédurale Aura v3.1 - Skills appris"}
        )

        # Modèle d'embedding (lazy loading)
        self._model: Optional[SentenceTransformer] = None

        # Cache JSON pour skills complets
        self.skills_file = self.storage_path / "skills.json"
        self._skills_cache: Dict[str, dict] = self._load_skills_cache()

    @property
    def model(self) -> SentenceTransformer:
        """Charge le modèle d'embedding à la demande."""
        if self._model is None:
            self._model = SentenceTransformer(MEMORY_CONFIG["embedding_model"])
        return self._model

    def _load_skills_cache(self) -> Dict[str, dict]:
        """Charge le cache de skills."""
        if self.skills_file.exists():
            try:
                return json.loads(self.skills_file.read_text())
            except Exception:
                return {}
        return {}

    def _save_skills_cache(self):
        """Sauvegarde le cache de skills."""
        self.skills_file.write_text(json.dumps(self._skills_cache, indent=2, ensure_ascii=False))

    def _get_embedding(self, text: str) -> List[float]:
        """Génère l'embedding pour un texte."""
        return self.model.encode(text, show_progress_bar=False).tolist()

    def _skill_to_text(self, skill: Skill) -> str:
        """Convertit un skill en texte pour l'embedding."""
        parts = [
            f"Skill: {skill.name}",
            f"Description: {skill.description}",
            f"Pattern: {skill.pattern}",
            f"Conditions: {', '.join(skill.trigger_conditions)}",
            f"Action: {skill.action_template}"
        ]
        return "\n".join(parts)

    def store(self, skill: Skill) -> str:
        """
        Stocke ou met à jour un skill.

        Args:
            skill: Le skill à stocker

        Returns:
            L'ID du skill
        """
        text = self._skill_to_text(skill)
        embedding = self._get_embedding(text)

        # Métadonnées pour ChromaDB
        chroma_metadata = {
            "name": skill.name,
            "description": skill.description[:200],
            "pattern_preview": skill.pattern[:200],
            "success_rate": skill.success_rate,
            "usage_count": skill.usage_count,
            "status": skill.metadata.status,
            "trigger_conditions": json.dumps(skill.trigger_conditions)
        }

        # Upsert dans ChromaDB
        self.collection.upsert(
            ids=[skill.id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[chroma_metadata]
        )

        # Stocker dans le cache JSON
        self._skills_cache[skill.id] = skill.to_dict()
        self._save_skills_cache()

        return skill.id

    def create_skill(
        self,
        name: str,
        description: str,
        pattern: str,
        trigger_conditions: List[str],
        action_template: str,
        source_episodes: Optional[List[str]] = None,
        success_rate: float = 0.0
    ) -> str:
        """
        Crée un nouveau skill.

        Args:
            name: Nom du skill
            description: Description
            pattern: Pattern général appris
            trigger_conditions: Conditions d'activation
            action_template: Template d'action
            source_episodes: IDs des épisodes sources
            success_rate: Taux de succès initial

        Returns:
            L'ID du skill créé
        """
        skill = Skill(
            id="",  # Généré automatiquement
            name=name,
            description=description,
            pattern=pattern,
            trigger_conditions=trigger_conditions,
            action_template=action_template,
            success_rate=success_rate,
            usage_count=0,
            source_episodes=source_episodes or [],
            metadata=MemoryMetadata(source="consolidation")
        )

        return self.store(skill)

    def find_applicable_skills(
        self,
        context: str,
        n_results: int = 3,
        min_success_rate: float = 0.0
    ) -> List[Tuple[Skill, MemoryScore]]:
        """
        Trouve les skills applicables pour un contexte donné.

        Args:
            context: Le contexte actuel
            n_results: Nombre maximum de résultats
            min_success_rate: Taux de succès minimum

        Returns:
            Liste de tuples (Skill, MemoryScore)
        """
        if self.collection.count() == 0:
            return []

        query_embedding = self._get_embedding(context)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results * 2, self.collection.count())
        )

        scored_results: List[Tuple[Skill, MemoryScore]] = []

        for i, skill_id in enumerate(results["ids"][0]):
            if skill_id not in self._skills_cache:
                continue

            skill = Skill.from_dict(self._skills_cache[skill_id])

            # Filtrer par taux de succès
            if skill.success_rate < min_success_rate:
                continue

            # Calculer le score
            similarity = 1 - (results["distances"][0][i] if results["distances"] else 0)
            recency = calculate_recency_score(
                skill.metadata.created_at,
                MEMORY_CONFIG["recency_decay_days"]
            )

            # Utiliser le success_rate comme importance
            score = MemoryScore(
                similarity=similarity,
                importance=skill.success_rate,
                recency=recency,
                access_frequency=min(skill.usage_count / 100, 1.0)  # Normaliser
            )

            scored_results.append((skill, score))

        scored_results.sort(key=lambda x: x[1].combined_score, reverse=True)
        return scored_results[:n_results]

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Récupère un skill par son ID."""
        if skill_id in self._skills_cache:
            return Skill.from_dict(self._skills_cache[skill_id])
        return None

    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        """Récupère un skill par son nom."""
        for data in self._skills_cache.values():
            if data.get("name") == name:
                return Skill.from_dict(data)
        return None

    def record_usage(
        self,
        skill_id: str,
        success: bool,
        context: Optional[str] = None
    ) -> bool:
        """
        Enregistre l'utilisation d'un skill et met à jour son taux de succès.

        Args:
            skill_id: ID du skill utilisé
            success: True si l'utilisation a réussi
            context: Contexte optionnel pour enrichir le skill

        Returns:
            True si la mise à jour a réussi
        """
        if skill_id not in self._skills_cache:
            return False

        skill_data = self._skills_cache[skill_id]
        usage_count = skill_data.get("usage_count", 0) + 1
        current_rate = skill_data.get("success_rate", 0.0)

        # Moyenne mobile pour le taux de succès
        new_success = 1.0 if success else 0.0
        # Pondération: les nouvelles utilisations comptent moins au fur et à mesure
        weight = 1 / usage_count
        new_rate = current_rate * (1 - weight) + new_success * weight

        skill_data["usage_count"] = usage_count
        skill_data["success_rate"] = new_rate
        skill_data["metadata"]["updated_at"] = datetime.now().isoformat()

        # Mettre à jour ChromaDB
        self.collection.update(
            ids=[skill_id],
            metadatas=[{"usage_count": usage_count, "success_rate": new_rate}]
        )

        self._save_skills_cache()
        return True

    def update_skill(
        self,
        skill_id: str,
        pattern: Optional[str] = None,
        trigger_conditions: Optional[List[str]] = None,
        action_template: Optional[str] = None
    ) -> bool:
        """Met à jour un skill existant."""
        if skill_id not in self._skills_cache:
            return False

        skill = Skill.from_dict(self._skills_cache[skill_id])

        if pattern:
            skill.pattern = pattern
        if trigger_conditions:
            skill.trigger_conditions = trigger_conditions
        if action_template:
            skill.action_template = action_template

        skill.metadata.updated_at = datetime.now().isoformat()

        # Re-stocker avec les nouvelles valeurs
        self.store(skill)
        return True

    def add_source_episode(self, skill_id: str, episode_id: str) -> bool:
        """Ajoute un épisode source à un skill."""
        if skill_id not in self._skills_cache:
            return False

        skill_data = self._skills_cache[skill_id]
        sources = skill_data.get("source_episodes", [])
        if episode_id not in sources:
            sources.append(episode_id)
            skill_data["source_episodes"] = sources
            skill_data["metadata"]["updated_at"] = datetime.now().isoformat()
            self._save_skills_cache()

        return True

    def delete_skill(self, skill_id: str) -> bool:
        """Supprime un skill."""
        if skill_id in self._skills_cache:
            del self._skills_cache[skill_id]
            self._save_skills_cache()

            try:
                self.collection.delete(ids=[skill_id])
            except Exception:
                pass
            return True
        return False

    def get_all_skills(self) -> List[Skill]:
        """Récupère tous les skills."""
        return [Skill.from_dict(data) for data in self._skills_cache.values()]

    def get_top_skills(self, limit: int = 10, by: str = "success_rate") -> List[Skill]:
        """
        Récupère les meilleurs skills.

        Args:
            limit: Nombre de skills
            by: Critère de tri (success_rate, usage_count)
        """
        skills = self.get_all_skills()

        if by == "success_rate":
            skills.sort(key=lambda s: s.success_rate, reverse=True)
        elif by == "usage_count":
            skills.sort(key=lambda s: s.usage_count, reverse=True)

        return skills[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de la mémoire procédurale."""
        skills = self.get_all_skills()
        total = len(skills)

        if total == 0:
            return {
                "total_skills": 0,
                "avg_success_rate": 0,
                "total_usages": 0,
                "storage_path": str(self.storage_path)
            }

        avg_success = sum(s.success_rate for s in skills) / total
        total_usages = sum(s.usage_count for s in skills)

        return {
            "total_skills": total,
            "avg_success_rate": round(avg_success, 2),
            "total_usages": total_usages,
            "top_skill": max(skills, key=lambda s: s.success_rate).name if skills else None,
            "most_used": max(skills, key=lambda s: s.usage_count).name if skills else None,
            "storage_path": str(self.storage_path),
            "chroma_count": self.collection.count()
        }


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aura Procedural Memory")
    subparsers = parser.add_subparsers(dest="command")

    # create
    create_p = subparsers.add_parser("create", help="Créer un skill")
    create_p.add_argument("--name", required=True)
    create_p.add_argument("--desc", required=True)
    create_p.add_argument("--pattern", required=True)
    create_p.add_argument("--conditions", nargs="+", required=True)
    create_p.add_argument("--action", required=True)

    # find
    find_p = subparsers.add_parser("find", help="Trouver des skills applicables")
    find_p.add_argument("context")
    find_p.add_argument("-n", type=int, default=3)

    # list
    list_p = subparsers.add_parser("list", help="Lister les skills")
    list_p.add_argument("--top", type=int, default=10)
    list_p.add_argument("--by", choices=["success_rate", "usage_count"], default="success_rate")

    # stats
    subparsers.add_parser("stats", help="Statistiques")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    memory = ProceduralMemory()

    if args.command == "create":
        skill_id = memory.create_skill(
            name=args.name,
            description=args.desc,
            pattern=args.pattern,
            trigger_conditions=args.conditions,
            action_template=args.action
        )
        print(f"Skill créé: {skill_id}")

    elif args.command == "find":
        results = memory.find_applicable_skills(args.context, n_results=args.n)
        if not results:
            print("Aucun skill applicable trouvé.")
        else:
            print(f"Trouvé {len(results)} skill(s):\n")
            for skill, score in results:
                print(f"[{skill.id}] {skill.name}")
                print(f"  Score: {score.combined_score:.3f} | Success: {skill.success_rate:.1%}")
                print(f"  Pattern: {skill.pattern[:80]}...")
                print(f"  Action: {skill.action_template[:80]}...")
                print()

    elif args.command == "list":
        skills = memory.get_top_skills(limit=args.top, by=args.by)
        print(f"Top {len(skills)} skills (par {args.by}):\n")
        for i, skill in enumerate(skills, 1):
            print(f"{i}. {skill.name}")
            print(f"   Success: {skill.success_rate:.1%} | Usages: {skill.usage_count}")
            print()

    elif args.command == "stats":
        stats = memory.get_stats()
        print("=== Mémoire Procédurale ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
