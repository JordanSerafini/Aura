#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Memory API - Interface CRUD unifiée pour la mémoire persistante.
Style Anthropic Memory Tool - fichiers mémoire gérés localement.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from memory_types import (
    MemoryType, MemoryPriority, MemoryMetadata, Episode, Skill, KnowledgeTriple,
    MEMORY_CONFIG
)
from episodic_memory import EpisodicMemory
from procedural_memory import ProceduralMemory
from knowledge_graph import KnowledgeGraph
from memory_consolidator import MemoryConsolidator


class MemoryAPI:
    """
    API unifiée pour toutes les opérations de mémoire.
    Point d'entrée unique pour interagir avec le système de mémoire Aura v3.1.
    """

    def __init__(self, base_path: Path | None = None):
        """Initialise l'API de mémoire."""
        self.base_path = base_path or Path.home() / ".aura" / "memory"
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Composants de mémoire (lazy loading)
        self._episodic: EpisodicMemory | None = None
        self._procedural: ProceduralMemory | None = None
        self._knowledge: KnowledgeGraph | None = None
        self._consolidator: MemoryConsolidator | None = None

        # Fichiers mémoire simples (style Anthropic)
        self.files_dir = self.base_path / "files"
        self.files_dir.mkdir(exist_ok=True)

    # === Lazy Loading des composants ===

    @property
    def episodic(self) -> EpisodicMemory:
        if self._episodic is None:
            self._episodic = EpisodicMemory(self.base_path / "episodic")
        return self._episodic

    @property
    def procedural(self) -> ProceduralMemory:
        if self._procedural is None:
            self._procedural = ProceduralMemory(self.base_path / "procedural")
        return self._procedural

    @property
    def knowledge(self) -> KnowledgeGraph:
        if self._knowledge is None:
            self._knowledge = KnowledgeGraph(self.base_path / "knowledge")
        return self._knowledge

    @property
    def consolidator(self) -> MemoryConsolidator:
        if self._consolidator is None:
            self._consolidator = MemoryConsolidator(
                self.episodic, self.procedural, self.knowledge
            )
        return self._consolidator

    # === API de fichiers mémoire (style Anthropic) ===

    def create_file(
        self,
        filename: str,
        content: str,
        metadata: dict[str, Any | None] = None
    ) -> dict[str, Any]:
        """
        Crée un nouveau fichier mémoire.

        Args:
            filename: Nom du fichier (sans chemin)
            content: Contenu du fichier
            metadata: Métadonnées optionnelles

        Returns:
            Infos sur le fichier créé
        """
        # Sanitize filename
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
        if not safe_name:
            safe_name = f"memory_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        file_path = self.files_dir / safe_name

        # Éviter les écrasements
        if file_path.exists():
            base, ext = os.path.splitext(safe_name)
            counter = 1
            while file_path.exists():
                file_path = self.files_dir / f"{base}_{counter}{ext}"
                counter += 1

        # Écrire le fichier
        file_path.write_text(content, encoding="utf-8")

        # Écrire les métadonnées
        meta = {
            "filename": file_path.name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "size": len(content),
            **(metadata or {})
        }
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        meta_path.write_text(json.dumps(meta, indent=2))

        return {
            "status": "created",
            "path": str(file_path),
            "filename": file_path.name,
            "size": len(content)
        }

    def read_file(self, filename: str) -> dict[str, Any]:
        """Lit un fichier mémoire."""
        file_path = self.files_dir / filename

        if not file_path.exists():
            return {"status": "error", "message": f"File not found: {filename}"}

        content = file_path.read_text(encoding="utf-8")

        # Charger les métadonnées si disponibles
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        metadata = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text())
            except Exception:
                pass

        return {
            "status": "success",
            "filename": filename,
            "content": content,
            "size": len(content),
            "metadata": metadata
        }

    def update_file(
        self,
        filename: str,
        content: str,
        append: bool = False
    ) -> dict[str, Any]:
        """Met à jour un fichier mémoire."""
        file_path = self.files_dir / filename

        if not file_path.exists():
            return {"status": "error", "message": f"File not found: {filename}"}

        if append:
            existing = file_path.read_text(encoding="utf-8")
            content = existing + "\n" + content

        file_path.write_text(content, encoding="utf-8")

        # Update metadata
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                meta["updated_at"] = datetime.now().isoformat()
                meta["size"] = len(content)
                meta_path.write_text(json.dumps(meta, indent=2))
            except Exception:
                pass

        return {
            "status": "updated",
            "filename": filename,
            "size": len(content),
            "appended": append
        }

    def delete_file(self, filename: str) -> dict[str, Any]:
        """Supprime un fichier mémoire."""
        file_path = self.files_dir / filename

        if not file_path.exists():
            return {"status": "error", "message": f"File not found: {filename}"}

        file_path.unlink()

        # Supprimer aussi les métadonnées
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        if meta_path.exists():
            meta_path.unlink()

        return {"status": "deleted", "filename": filename}

    def list_files(self) -> dict[str, Any]:
        """Liste tous les fichiers mémoire."""
        files = []
        for file_path in self.files_dir.iterdir():
            if file_path.suffix == ".meta":
                continue
            if file_path.is_file():
                files.append({
                    "filename": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(
                        file_path.stat().st_mtime
                    ).isoformat()
                })

        return {
            "status": "success",
            "count": len(files),
            "files": sorted(files, key=lambda x: x["modified"], reverse=True)
        }

    # === API Épisodique ===

    def record_episode(
        self,
        context: str,
        action: str,
        outcome: str,
        thought_process: str = "",
        entities: list[str | None] = None,
        importance: float = 0.5,
        valence: float = 0.0
    ) -> dict[str, Any]:
        """
        Enregistre un épisode dans la mémoire épisodique.

        Args:
            context: Contexte de l'interaction
            action: Action effectuée
            outcome: Résultat
            thought_process: Raisonnement
            entities: Entités impliquées
            importance: Importance (0-1)
            valence: Valence émotionnelle (-1 à +1)

        Returns:
            ID et détails de l'épisode créé
        """
        episode_id = self.episodic.record_interaction(
            context=context,
            action=action,
            outcome=outcome,
            thought_process=thought_process,
            entities=entities,
            importance=importance,
            emotional_valence=valence
        )

        return {
            "status": "recorded",
            "episode_id": episode_id,
            "type": "episodic"
        }

    def recall_episodes(
        self,
        query: str,
        n_results: int = 5,
        min_importance: float = 0.0
    ) -> dict[str, Any]:
        """Rappelle des épisodes pertinents."""
        results = self.episodic.recall(
            query=query,
            n_results=n_results,
            min_importance=min_importance
        )

        episodes_data = []
        for episode, score in results:
            episodes_data.append({
                "id": episode.id,
                "context": episode.context,
                "action": episode.action,
                "outcome": episode.outcome,
                "timestamp": episode.timestamp,
                "score": score.combined_score,
                "scores": score.to_dict()
            })

        return {
            "status": "success",
            "query": query,
            "count": len(episodes_data),
            "episodes": episodes_data
        }

    # === API Procédurale ===

    def find_skills(
        self,
        context: str,
        n_results: int = 3
    ) -> dict[str, Any]:
        """Trouve les skills applicables pour un contexte."""
        results = self.procedural.find_applicable_skills(
            context=context,
            n_results=n_results
        )

        skills_data = []
        for skill, score in results:
            skills_data.append({
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "pattern": skill.pattern,
                "action_template": skill.action_template,
                "success_rate": skill.success_rate,
                "score": score.combined_score
            })

        return {
            "status": "success",
            "context": context,
            "count": len(skills_data),
            "skills": skills_data
        }

    def record_skill_usage(
        self,
        skill_id: str,
        success: bool
    ) -> dict[str, Any]:
        """Enregistre l'utilisation d'un skill."""
        result = self.procedural.record_usage(skill_id, success)
        return {
            "status": "recorded" if result else "error",
            "skill_id": skill_id,
            "success": success
        }

    # === API Knowledge Graph ===

    def add_knowledge(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0
    ) -> dict[str, Any]:
        """Ajoute un triplet de connaissance."""
        triple_id = self.knowledge.add_triple(
            subject=subject,
            predicate=predicate,
            obj=obj,
            confidence=confidence
        )

        return {
            "status": "added",
            "triple_id": triple_id,
            "triple": f"{subject} --[{predicate}]--> {obj}"
        }

    def query_knowledge(
        self,
        query: str,
        n_results: int = 5
    ) -> dict[str, Any]:
        """Recherche sémantique dans le graphe."""
        results = self.knowledge.query_semantic(query, n_results)

        triples_data = []
        for triple, score in results:
            triples_data.append({
                "id": triple.id,
                "subject": triple.subject,
                "predicate": triple.predicate,
                "object": triple.object,
                "confidence": triple.confidence,
                "score": score
            })

        return {
            "status": "success",
            "query": query,
            "count": len(triples_data),
            "triples": triples_data
        }

    def get_entity_relations(
        self,
        entity: str,
        direction: str = "both"
    ) -> dict[str, Any]:
        """Récupère les relations d'une entité."""
        triples = self.knowledge.get_relations(entity, direction)

        return {
            "status": "success",
            "entity": entity,
            "direction": direction,
            "count": len(triples),
            "relations": [
                {
                    "subject": t.subject,
                    "predicate": t.predicate,
                    "object": t.object
                }
                for t in triples
            ]
        }

    # === API Consolidation ===

    def consolidate(
        self,
        dry_run: bool = False
    ) -> dict[str, Any]:
        """Lance une consolidation de la mémoire."""
        result = self.consolidator.consolidate(dry_run=dry_run)

        return {
            "status": "completed",
            "dry_run": dry_run,
            "episodes_processed": result.episodes_processed,
            "skills_created": result.skills_created,
            "skills_updated": result.skills_updated,
            "triples_extracted": result.triples_extracted,
            "episodes_archived": result.episodes_archived
        }

    def analyze_patterns(self) -> dict[str, Any]:
        """Analyse les patterns pour la consolidation."""
        return self.consolidator.analyze_patterns()

    # === API Générale ===

    def remember(
        self,
        content: str,
        memory_type: str = "note",
        importance: float = 0.5,
        tags: list[str | None] = None
    ) -> dict[str, Any]:
        """
        Méthode simplifiée pour mémoriser quelque chose.
        Choisit automatiquement le bon type de stockage.

        Args:
            content: Ce qu'il faut mémoriser
            memory_type: Type (note, fact, preference, episode)
            importance: Importance (0-1)
            tags: Tags optionnels

        Returns:
            Confirmation avec ID
        """
        if memory_type == "episode":
            return self.record_episode(
                context="Mémorisation directe",
                action="remember",
                outcome=content,
                importance=importance
            )

        elif memory_type == "fact":
            # Extraire sujet-prédicat-objet si possible
            parts = content.split(" est ", 1)
            if len(parts) == 2:
                return self.add_knowledge(
                    subject=parts[0].strip(),
                    predicate="is",
                    obj=parts[1].strip(),
                    confidence=importance
                )

        # Par défaut: fichier mémoire
        filename = f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        return self.create_file(
            filename=filename,
            content=content,
            metadata={"type": memory_type, "importance": importance, "tags": tags or []}
        )

    def search(
        self,
        query: str,
        memory_types: list[str | None] = None,
        n_results: int = 5
    ) -> dict[str, Any]:
        """
        Recherche unifiée dans tous les types de mémoire.

        Args:
            query: Requête de recherche
            memory_types: Types à chercher (episodic, procedural, knowledge, files)
            n_results: Nombre de résultats par type

        Returns:
            Résultats agrégés
        """
        types = memory_types or ["episodic", "procedural", "knowledge"]
        results = {}

        if "episodic" in types:
            ep_results = self.recall_episodes(query, n_results)
            results["episodic"] = ep_results.get("episodes", [])

        if "procedural" in types:
            sk_results = self.find_skills(query, n_results)
            results["procedural"] = sk_results.get("skills", [])

        if "knowledge" in types:
            kg_results = self.query_knowledge(query, n_results)
            results["knowledge"] = kg_results.get("triples", [])

        return {
            "status": "success",
            "query": query,
            "results": results
        }

    def get_stats(self) -> dict[str, Any]:
        """Statistiques complètes du système de mémoire."""
        stats = {
            "episodic": self.episodic.get_stats(),
            "procedural": self.procedural.get_stats(),
            "knowledge": self.knowledge.get_stats(),
            "files": self.list_files(),
            "version": "3.1.0"
        }
        return stats


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aura Memory API v3.1")
    subparsers = parser.add_subparsers(dest="command")

    # remember
    rem_p = subparsers.add_parser("remember", help="Mémoriser quelque chose")
    rem_p.add_argument("content")
    rem_p.add_argument("--type", choices=["note", "fact", "episode"], default="note")
    rem_p.add_argument("--importance", type=float, default=0.5)

    # search
    search_p = subparsers.add_parser("search", help="Recherche unifiée")
    search_p.add_argument("query")
    search_p.add_argument("-n", type=int, default=5)

    # files
    files_p = subparsers.add_parser("files", help="Gestion des fichiers mémoire")
    files_sub = files_p.add_subparsers(dest="files_cmd")
    files_sub.add_parser("list", help="Lister les fichiers")
    read_p = files_sub.add_parser("read", help="Lire un fichier")
    read_p.add_argument("filename")
    create_p = files_sub.add_parser("create", help="Créer un fichier")
    create_p.add_argument("filename")
    create_p.add_argument("content")

    # consolidate
    cons_p = subparsers.add_parser("consolidate", help="Consolider la mémoire")
    cons_p.add_argument("--dry-run", action="store_true")

    # stats
    subparsers.add_parser("stats", help="Statistiques")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    api = MemoryAPI()

    if args.command == "remember":
        result = api.remember(
            content=args.content,
            memory_type=args.type,
            importance=args.importance
        )
        print(json.dumps(result, indent=2))

    elif args.command == "search":
        result = api.search(args.query, n_results=args.n)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "files":
        if args.files_cmd == "list":
            result = api.list_files()
            print(json.dumps(result, indent=2))
        elif args.files_cmd == "read":
            result = api.read_file(args.filename)
            print(json.dumps(result, indent=2))
        elif args.files_cmd == "create":
            result = api.create_file(args.filename, args.content)
            print(json.dumps(result, indent=2))
        else:
            files_p.print_help()

    elif args.command == "consolidate":
        result = api.consolidate(dry_run=args.dry_run)
        print(json.dumps(result, indent=2))

    elif args.command == "stats":
        stats = api.get_stats()
        print(json.dumps(stats, indent=2, default=str))
