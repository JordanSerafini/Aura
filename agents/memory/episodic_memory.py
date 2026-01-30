#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Episodic Memory - Mémoire épisodique avec contexte complet et scoring avancé.
Capture et rappelle les interactions passées avec leur contexte intégral.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Ajout du path pour imports locaux
sys.path.insert(0, str(Path(__file__).parent))
from memory_types import (
    Episode, MemoryMetadata, MemoryScore, MemoryStatus, MemoryPriority,
    MEMORY_CONFIG, calculate_recency_score, generate_memory_id
)


class EpisodicMemory:
    """
    Gestionnaire de mémoire épisodique.
    Stocke les interactions complètes avec contexte, action, résultat et raisonnement.
    """

    COLLECTION_NAME = "episodes"

    def __init__(self, storage_path: Path | None = None):
        """Initialise la mémoire épisodique."""
        self.storage_path = storage_path or Path.home() / ".aura" / "memory" / "episodic"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # ChromaDB pour stockage vectoriel
        self.client = chromadb.PersistentClient(
            path=str(self.storage_path / "chroma_db"),
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Mémoire épisodique Aura v3.1"}
        )

        # Modèle d'embedding (lazy loading)
        self._model: SentenceTransformer | None = None

        # Cache JSON pour métadonnées étendues
        self.metadata_file = self.storage_path / "episodes_metadata.json"
        self._metadata_cache: dict[str, dict] = self._load_metadata_cache()

    @property
    def model(self) -> SentenceTransformer:
        """Charge le modèle d'embedding à la demande."""
        if self._model is None:
            self._model = SentenceTransformer(MEMORY_CONFIG["embedding_model"])
        return self._model

    def _load_metadata_cache(self) -> dict[str, dict]:
        """Charge le cache de métadonnées depuis le fichier JSON."""
        if self.metadata_file.exists():
            try:
                return json.loads(self.metadata_file.read_text())
            except Exception:
                return {}
        return {}

    def _save_metadata_cache(self):
        """Sauvegarde le cache de métadonnées."""
        self.metadata_file.write_text(json.dumps(self._metadata_cache, indent=2))

    def _get_embedding(self, text: str) -> list[float]:
        """Génère l'embedding pour un texte."""
        return self.model.encode(text, show_progress_bar=False).tolist()

    def _episode_to_text(self, episode: Episode) -> str:
        """Convertit un épisode en texte pour l'embedding."""
        parts = [
            f"Contexte: {episode.context}",
            f"Action: {episode.action}",
            f"Résultat: {episode.outcome}",
            f"Raisonnement: {episode.thought_process}"
        ]
        if episode.entities:
            parts.append(f"Entités: {', '.join(episode.entities)}")
        return "\n".join(parts)

    def store(self, episode: Episode) -> str:
        """
        Stocke un nouvel épisode en mémoire.

        Args:
            episode: L'épisode à stocker

        Returns:
            L'ID de l'épisode stocké
        """
        # Générer le texte pour l'embedding
        text = self._episode_to_text(episode)
        embedding = self._get_embedding(text)

        # Préparer les métadonnées pour ChromaDB (flat)
        chroma_metadata = {
            "timestamp": episode.timestamp,
            "context_preview": episode.context[:200],
            "action_preview": episode.action[:200],
            "outcome_preview": episode.outcome[:200],
            "importance": episode.importance,
            "emotional_valence": episode.emotional_valence,
            "status": episode.metadata.status,
            "priority": episode.metadata.priority,
            "source": episode.metadata.source,
            "entities": json.dumps(episode.entities)
        }

        # Upsert dans ChromaDB
        self.collection.upsert(
            ids=[episode.id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[chroma_metadata]
        )

        # Stocker les métadonnées complètes dans le cache JSON
        self._metadata_cache[episode.id] = episode.to_dict()
        self._save_metadata_cache()

        return episode.id

    def record_interaction(
        self,
        context: str,
        action: str,
        outcome: str,
        thought_process: str = "",
        entities: list[str | None] = None,
        importance: float = 0.5,
        emotional_valence: float = 0.0,
        source: str = "user"
    ) -> str:
        """
        Enregistre une nouvelle interaction comme épisode.

        Args:
            context: Le contexte/situation de l'interaction
            action: L'action effectuée
            outcome: Le résultat de l'action
            thought_process: Le raisonnement derrière l'action
            entities: Les entités impliquées
            importance: Importance de 0 à 1
            emotional_valence: Valence de -1 (négatif) à +1 (positif)
            source: Source de l'épisode (user, agent, system)

        Returns:
            L'ID de l'épisode créé
        """
        episode = Episode(
            id="",  # Sera généré automatiquement
            timestamp=datetime.now().isoformat(),
            context=context,
            action=action,
            outcome=outcome,
            thought_process=thought_process or f"Action: {action}",
            entities=entities or [],
            importance=importance,
            emotional_valence=emotional_valence,
            metadata=MemoryMetadata(source=source)
        )

        return self.store(episode)

    def recall(
        self,
        query: str,
        n_results: int = 5,
        min_importance: float = 0.0,
        include_archived: bool = False
    ) -> list[tuple[Episode, MemoryScore]]:
        """
        Rappelle les épisodes pertinents avec scoring avancé.

        Args:
            query: Requête de recherche
            n_results: Nombre maximum de résultats
            min_importance: Importance minimale requise
            include_archived: Inclure les épisodes archivés

        Returns:
            Liste de tuples (Episode, MemoryScore) triés par score combiné
        """
        if self.collection.count() == 0:
            return []

        # Recherche vectorielle
        query_embedding = self._get_embedding(query)

        # Requête ChromaDB
        where_filter = None
        if not include_archived:
            where_filter = {"status": {"$ne": MemoryStatus.ARCHIVED.name}}

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results * 2, self.collection.count()),  # Over-fetch pour filtrer
            where=where_filter
        )

        # Construire les résultats avec scoring
        scored_results: list[tuple[Episode, MemoryScore]] = []

        for i, doc_id in enumerate(results["ids"][0]):
            # Récupérer l'épisode complet depuis le cache
            if doc_id not in self._metadata_cache:
                continue

            episode_data = self._metadata_cache[doc_id]
            episode = Episode.from_dict(episode_data)

            # Filtrer par importance
            if episode.importance < min_importance:
                continue

            # Calculer le score
            similarity = 1 - (results["distances"][0][i] if results["distances"] else 0)
            recency = calculate_recency_score(
                episode.timestamp,
                MEMORY_CONFIG["recency_decay_days"]
            )

            # Fréquence d'accès normalisée
            max_access = max((e.get("metadata", {}).get("access_count", 1)
                            for e in self._metadata_cache.values()), default=1)
            access_freq = episode.metadata.access_count / max_access if max_access > 0 else 0

            score = MemoryScore(
                similarity=similarity,
                importance=episode.importance,
                recency=recency,
                access_frequency=access_freq
            )

            scored_results.append((episode, score))

            # Mettre à jour les stats d'accès
            self._update_access_stats(doc_id)

        # Trier par score combiné et limiter
        scored_results.sort(key=lambda x: x[1].combined_score, reverse=True)
        return scored_results[:n_results]

    def _update_access_stats(self, episode_id: str):
        """Met à jour les statistiques d'accès d'un épisode."""
        if episode_id in self._metadata_cache:
            meta = self._metadata_cache[episode_id].get("metadata", {})
            meta["access_count"] = meta.get("access_count", 0) + 1
            meta["last_accessed"] = datetime.now().isoformat()
            self._metadata_cache[episode_id]["metadata"] = meta
            # Sauvegarde différée pour performance
            # self._save_metadata_cache()

    def get_episode(self, episode_id: str) -> Episode | None:
        """Récupère un épisode par son ID."""
        if episode_id in self._metadata_cache:
            self._update_access_stats(episode_id)
            return Episode.from_dict(self._metadata_cache[episode_id])
        return None

    def get_recent_episodes(self, limit: int = 10) -> list[Episode]:
        """Récupère les épisodes les plus récents."""
        episodes = []
        for data in self._metadata_cache.values():
            episode = Episode.from_dict(data)
            if episode.metadata.status != MemoryStatus.ARCHIVED.name:
                episodes.append(episode)

        # Trier par timestamp décroissant
        episodes.sort(key=lambda e: e.timestamp, reverse=True)
        return episodes[:limit]

    def get_successful_episodes(
        self,
        min_valence: float = 0.3,
        limit: int = 20
    ) -> list[Episode]:
        """
        Récupère les épisodes avec résultat positif.
        Utile pour la consolidation en skills.
        """
        episodes = []
        for data in self._metadata_cache.values():
            episode = Episode.from_dict(data)
            if (episode.emotional_valence >= min_valence and
                episode.metadata.status == MemoryStatus.ACTIVE.name):
                episodes.append(episode)

        episodes.sort(key=lambda e: e.emotional_valence, reverse=True)
        return episodes[:limit]

    def archive_episode(self, episode_id: str) -> bool:
        """Archive un épisode (ne le supprime pas, mais le marque comme archivé)."""
        if episode_id in self._metadata_cache:
            self._metadata_cache[episode_id]["metadata"]["status"] = MemoryStatus.ARCHIVED.name
            self._metadata_cache[episode_id]["metadata"]["updated_at"] = datetime.now().isoformat()
            self._save_metadata_cache()

            # Mettre à jour dans ChromaDB
            self.collection.update(
                ids=[episode_id],
                metadatas=[{"status": MemoryStatus.ARCHIVED.name}]
            )
            return True
        return False

    def mark_consolidated(self, episode_ids: list[str], skill_id: str) -> int:
        """Marque des épisodes comme consolidés dans un skill."""
        count = 0
        for ep_id in episode_ids:
            if ep_id in self._metadata_cache:
                self._metadata_cache[ep_id]["metadata"]["status"] = MemoryStatus.CONSOLIDATED.name
                self._metadata_cache[ep_id]["metadata"]["updated_at"] = datetime.now().isoformat()
                # Ajouter référence au skill
                self._metadata_cache[ep_id].setdefault("consolidated_into", []).append(skill_id)
                count += 1

        if count > 0:
            self._save_metadata_cache()
        return count

    def delete_episode(self, episode_id: str) -> bool:
        """Supprime définitivement un épisode."""
        if episode_id in self._metadata_cache:
            del self._metadata_cache[episode_id]
            self._save_metadata_cache()

            try:
                self.collection.delete(ids=[episode_id])
            except Exception:
                pass
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Retourne les statistiques de la mémoire épisodique."""
        total = len(self._metadata_cache)
        active = sum(1 for e in self._metadata_cache.values()
                    if e.get("metadata", {}).get("status") == MemoryStatus.ACTIVE.name)
        archived = sum(1 for e in self._metadata_cache.values()
                      if e.get("metadata", {}).get("status") == MemoryStatus.ARCHIVED.name)
        consolidated = sum(1 for e in self._metadata_cache.values()
                         if e.get("metadata", {}).get("status") == MemoryStatus.CONSOLIDATED.name)

        # Calcul de la moyenne d'importance
        importances = [e.get("importance", 0.5) for e in self._metadata_cache.values()]
        avg_importance = sum(importances) / len(importances) if importances else 0

        return {
            "total_episodes": total,
            "active": active,
            "archived": archived,
            "consolidated": consolidated,
            "avg_importance": round(avg_importance, 2),
            "storage_path": str(self.storage_path),
            "chroma_count": self.collection.count()
        }

    def flush_access_stats(self):
        """Force la sauvegarde des statistiques d'accès."""
        self._save_metadata_cache()


# CLI pour tests
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aura Episodic Memory")
    subparsers = parser.add_subparsers(dest="command")

    # record
    record_p = subparsers.add_parser("record", help="Enregistrer un épisode")
    record_p.add_argument("--context", required=True)
    record_p.add_argument("--action", required=True)
    record_p.add_argument("--outcome", required=True)
    record_p.add_argument("--thought", default="")
    record_p.add_argument("--importance", type=float, default=0.5)

    # recall
    recall_p = subparsers.add_parser("recall", help="Rappeler des épisodes")
    recall_p.add_argument("query")
    recall_p.add_argument("-n", type=int, default=5)

    # stats
    subparsers.add_parser("stats", help="Statistiques")

    # recent
    recent_p = subparsers.add_parser("recent", help="Épisodes récents")
    recent_p.add_argument("-n", type=int, default=5)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    memory = EpisodicMemory()

    if args.command == "record":
        ep_id = memory.record_interaction(
            context=args.context,
            action=args.action,
            outcome=args.outcome,
            thought_process=args.thought,
            importance=args.importance
        )
        print(f"Épisode enregistré: {ep_id}")

    elif args.command == "recall":
        results = memory.recall(args.query, n_results=args.n)
        if not results:
            print("Aucun épisode trouvé.")
        else:
            print(f"Trouvé {len(results)} épisode(s):\n")
            for episode, score in results:
                print(f"[{episode.id}] Score: {score.combined_score:.3f}")
                print(f"  Contexte: {episode.context[:100]}...")
                print(f"  Action: {episode.action[:100]}...")
                print(f"  Résultat: {episode.outcome[:100]}...")
                print()

    elif args.command == "stats":
        stats = memory.get_stats()
        print("=== Mémoire Épisodique ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")

    elif args.command == "recent":
        episodes = memory.get_recent_episodes(limit=args.n)
        print(f"{len(episodes)} épisode(s) récent(s):\n")
        for ep in episodes:
            print(f"[{ep.id}] {ep.timestamp}")
            print(f"  {ep.context[:80]}...")
            print()
