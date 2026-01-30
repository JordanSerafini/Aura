#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Knowledge Graph - Graphe de connaissances style AriGraph.
Stocke les triplets (sujet, relation, objet) avec liens vers la mémoire épisodique.
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).parent))
from memory_types import (
    KnowledgeTriple, MemoryMetadata, MemoryScore,
    MEMORY_CONFIG, calculate_recency_score
)


class KnowledgeGraph:
    """
    Gestionnaire du graphe de connaissances.
    Stocke des triplets et permet la navigation relationnelle.
    """

    COLLECTION_NAME = "knowledge"

    # Types de relations prédéfinis
    RELATION_TYPES = {
        # Relations d'entités
        "is_a": "Est un type de",
        "has": "Possède",
        "part_of": "Fait partie de",
        "located_in": "Situé dans",
        "created_by": "Créé par",
        "uses": "Utilise",
        "depends_on": "Dépend de",
        # Relations d'actions
        "can": "Peut",
        "does": "Fait",
        "causes": "Cause",
        "requires": "Requiert",
        # Relations temporelles
        "before": "Avant",
        "after": "Après",
        "during": "Pendant",
        # Relations de préférence
        "prefers": "Préfère",
        "avoids": "Évite",
        "likes": "Aime",
        # Relations techniques
        "implements": "Implémente",
        "extends": "Étend",
        "calls": "Appelle",
        "returns": "Retourne"
    }

    def __init__(self, storage_path: Path | None = None):
        """Initialise le graphe de connaissances."""
        self.storage_path = storage_path or Path.home() / ".aura" / "memory" / "knowledge"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # ChromaDB pour recherche vectorielle
        self.client = chromadb.PersistentClient(
            path=str(self.storage_path / "chroma_db"),
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Graphe de connaissances Aura v3.1"}
        )

        # Modèle d'embedding
        self._model: SentenceTransformer | None = None

        # Index du graphe (adjacency lists)
        self.graph_file = self.storage_path / "graph.json"
        self._graph: dict[str, dict] = self._load_graph()

        # Index inversé pour recherche rapide
        self._subject_index: dict[str, set[str]] = defaultdict(set)
        self._object_index: dict[str, set[str]] = defaultdict(set)
        self._predicate_index: dict[str, set[str]] = defaultdict(set)
        self._rebuild_indices()

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(MEMORY_CONFIG["embedding_model"])
        return self._model

    def _load_graph(self) -> dict[str, dict]:
        """Charge le graphe depuis le fichier."""
        if self.graph_file.exists():
            try:
                return json.loads(self.graph_file.read_text())
            except Exception:
                return {}
        return {}

    def _save_graph(self):
        """Sauvegarde le graphe."""
        self.graph_file.write_text(json.dumps(self._graph, indent=2, ensure_ascii=False))

    def _rebuild_indices(self):
        """Reconstruit les indices de recherche."""
        self._subject_index.clear()
        self._object_index.clear()
        self._predicate_index.clear()

        for triple_id, data in self._graph.items():
            self._subject_index[data["subject"].lower()].add(triple_id)
            self._object_index[data["object"].lower()].add(triple_id)
            self._predicate_index[data["predicate"].lower()].add(triple_id)

    def _get_embedding(self, text: str) -> list[float]:
        return self.model.encode(text, show_progress_bar=False).tolist()

    def add_triple(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        source_episode: str | None = None
    ) -> str:
        """
        Ajoute un triplet au graphe.

        Args:
            subject: Sujet (entité source)
            predicate: Prédicat (type de relation)
            obj: Objet (entité cible)
            confidence: Confiance dans ce triplet (0-1)
            source_episode: ID de l'épisode source

        Returns:
            ID du triplet créé
        """
        triple = KnowledgeTriple(
            id="",  # Généré automatiquement
            subject=subject,
            predicate=predicate,
            object=obj,
            confidence=confidence,
            source_episode=source_episode,
            metadata=MemoryMetadata(source="extraction" if source_episode else "user")
        )

        # Vérifier si ce triplet existe déjà
        existing_id = self._find_existing_triple(subject, predicate, obj)
        if existing_id:
            # Mettre à jour la confiance si le nouveau est plus élevé
            if confidence > self._graph[existing_id].get("confidence", 0):
                self._graph[existing_id]["confidence"] = confidence
                self._graph[existing_id]["metadata"]["updated_at"] = datetime.now().isoformat()
                self._save_graph()
            return existing_id

        # Stocker dans ChromaDB
        text = triple.to_text()
        embedding = self._get_embedding(text)

        chroma_metadata = {
            "subject": triple.subject,
            "predicate": triple.predicate,
            "object": triple.object,
            "confidence": triple.confidence,
            "source_episode": triple.source_episode or ""
        }

        self.collection.upsert(
            ids=[triple.id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[chroma_metadata]
        )

        # Stocker dans le graphe JSON
        self._graph[triple.id] = triple.to_dict()
        self._save_graph()

        # Mettre à jour les indices
        self._subject_index[subject.lower()].add(triple.id)
        self._object_index[obj.lower()].add(triple.id)
        self._predicate_index[predicate.lower()].add(triple.id)

        return triple.id

    def _find_existing_triple(self, subject: str, predicate: str, obj: str) -> str | None:
        """Trouve un triplet existant identique."""
        subject_matches = self._subject_index.get(subject.lower(), set())
        for triple_id in subject_matches:
            data = self._graph.get(triple_id, {})
            if (data.get("predicate", "").lower() == predicate.lower() and
                data.get("object", "").lower() == obj.lower()):
                return triple_id
        return None

    def extract_triples_from_text(self, text: str, source_episode: str | None = None) -> list[str]:
        """
        Extrait automatiquement des triplets depuis du texte.
        Utilise des patterns simples pour l'extraction.

        Args:
            text: Texte à analyser
            source_episode: ID de l'épisode source

        Returns:
            Liste des IDs de triplets créés
        """
        created_ids = []

        # Patterns d'extraction simples
        patterns = [
            # "X est un Y"
            (r"(\w+(?:\s+\w+)?)\s+est\s+un[e]?\s+(\w+(?:\s+\w+)?)", "is_a"),
            # "X utilise Y"
            (r"(\w+(?:\s+\w+)?)\s+utilise\s+(\w+(?:\s+\w+)?)", "uses"),
            # "X dépend de Y"
            (r"(\w+(?:\s+\w+)?)\s+dépend\s+de\s+(\w+(?:\s+\w+)?)", "depends_on"),
            # "X préfère Y"
            (r"l'?utilisateur\s+préfère\s+(\w+(?:\s+\w+)?)", "prefers", "utilisateur"),
            # "X a Y"
            (r"(\w+(?:\s+\w+)?)\s+a\s+(\w+(?:\s+\w+)?)", "has"),
            # "X peut Y"
            (r"(\w+(?:\s+\w+)?)\s+peut\s+(\w+(?:\s+\w+)?)", "can"),
        ]

        for pattern_tuple in patterns:
            if len(pattern_tuple) == 3:
                pattern, predicate, default_subject = pattern_tuple
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    obj = match.group(1)
                    triple_id = self.add_triple(
                        default_subject, predicate, obj, 0.7, source_episode
                    )
                    created_ids.append(triple_id)
            else:
                pattern, predicate = pattern_tuple
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    subject = match.group(1)
                    obj = match.group(2)
                    triple_id = self.add_triple(
                        subject, predicate, obj, 0.7, source_episode
                    )
                    created_ids.append(triple_id)

        return created_ids

    def query_semantic(
        self,
        query: str,
        n_results: int = 10
    ) -> list[tuple[KnowledgeTriple, float]]:
        """
        Recherche sémantique dans le graphe.

        Args:
            query: Requête de recherche
            n_results: Nombre de résultats

        Returns:
            Liste de tuples (triple, score)
        """
        if self.collection.count() == 0:
            return []

        query_embedding = self._get_embedding(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, self.collection.count())
        )

        triples_with_scores = []
        for i, triple_id in enumerate(results["ids"][0]):
            if triple_id not in self._graph:
                continue

            triple = KnowledgeTriple.from_dict(self._graph[triple_id])
            distance = results["distances"][0][i] if results["distances"] else 0
            score = 1 - distance

            triples_with_scores.append((triple, score))

        return triples_with_scores

    def get_relations(self, entity: str, direction: str = "both") -> list[KnowledgeTriple]:
        """
        Récupère toutes les relations d'une entité.

        Args:
            entity: L'entité à chercher
            direction: "outgoing" (sujet), "incoming" (objet), ou "both"

        Returns:
            Liste de triplets
        """
        triples = []
        entity_lower = entity.lower()

        if direction in ("outgoing", "both"):
            for triple_id in self._subject_index.get(entity_lower, set()):
                if triple_id in self._graph:
                    triples.append(KnowledgeTriple.from_dict(self._graph[triple_id]))

        if direction in ("incoming", "both"):
            for triple_id in self._object_index.get(entity_lower, set()):
                if triple_id in self._graph:
                    triples.append(KnowledgeTriple.from_dict(self._graph[triple_id]))

        return triples

    def get_by_predicate(self, predicate: str) -> list[KnowledgeTriple]:
        """Récupère tous les triplets avec un prédicat donné."""
        triples = []
        for triple_id in self._predicate_index.get(predicate.lower(), set()):
            if triple_id in self._graph:
                triples.append(KnowledgeTriple.from_dict(self._graph[triple_id]))
        return triples

    def traverse(
        self,
        start_entity: str,
        max_depth: int = 2,
        predicates: list[str | None] = None
    ) -> dict[str, list[KnowledgeTriple]]:
        """
        Traverse le graphe à partir d'une entité.

        Args:
            start_entity: Point de départ
            max_depth: Profondeur maximale
            predicates: Filtrer par types de relations

        Returns:
            Dict avec les niveaux de profondeur comme clés
        """
        result = defaultdict(list)
        visited = {start_entity.lower()}
        current_level = [start_entity]

        for depth in range(max_depth):
            next_level = []
            for entity in current_level:
                relations = self.get_relations(entity, direction="outgoing")
                for triple in relations:
                    if predicates and triple.predicate.lower() not in [p.lower() for p in predicates]:
                        continue

                    result[f"depth_{depth + 1}"].append(triple)

                    # Ajouter l'objet au prochain niveau s'il n'a pas été visité
                    obj_lower = triple.object.lower()
                    if obj_lower not in visited:
                        visited.add(obj_lower)
                        next_level.append(triple.object)

            current_level = next_level
            if not current_level:
                break

        return dict(result)

    def get_path(
        self,
        source: str,
        target: str,
        max_depth: int = 4
    ) -> list[KnowledgeTriple | None]:
        """
        Trouve un chemin entre deux entités.

        Args:
            source: Entité de départ
            target: Entité cible
            max_depth: Profondeur maximale de recherche

        Returns:
            Liste de triplets formant le chemin, ou None
        """
        from collections import deque

        source_lower = source.lower()
        target_lower = target.lower()

        if source_lower == target_lower:
            return []

        # BFS pour trouver le chemin le plus court
        queue = deque([(source, [])])
        visited = {source_lower}

        while queue:
            current, path = queue.popleft()

            if len(path) >= max_depth:
                continue

            for triple in self.get_relations(current, direction="outgoing"):
                obj_lower = triple.object.lower()

                if obj_lower == target_lower:
                    return path + [triple]

                if obj_lower not in visited:
                    visited.add(obj_lower)
                    queue.append((triple.object, path + [triple]))

        return None

    def delete_triple(self, triple_id: str) -> bool:
        """Supprime un triplet."""
        if triple_id not in self._graph:
            return False

        data = self._graph[triple_id]

        # Retirer des indices
        self._subject_index[data["subject"].lower()].discard(triple_id)
        self._object_index[data["object"].lower()].discard(triple_id)
        self._predicate_index[data["predicate"].lower()].discard(triple_id)

        # Supprimer
        del self._graph[triple_id]
        self._save_graph()

        try:
            self.collection.delete(ids=[triple_id])
        except Exception:
            pass

        return True

    def get_all_entities(self) -> set[str]:
        """Récupère toutes les entités uniques du graphe."""
        entities = set()
        for data in self._graph.values():
            entities.add(data["subject"])
            entities.add(data["object"])
        return entities

    def get_stats(self) -> dict[str, Any]:
        """Retourne les statistiques du graphe."""
        total_triples = len(self._graph)
        entities = self.get_all_entities()

        predicate_counts = defaultdict(int)
        for data in self._graph.values():
            predicate_counts[data["predicate"]] += 1

        return {
            "total_triples": total_triples,
            "unique_entities": len(entities),
            "unique_predicates": len(predicate_counts),
            "top_predicates": dict(sorted(predicate_counts.items(), key=lambda x: -x[1])[:5]),
            "storage_path": str(self.storage_path),
            "chroma_count": self.collection.count()
        }


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aura Knowledge Graph")
    subparsers = parser.add_subparsers(dest="command")

    # add
    add_p = subparsers.add_parser("add", help="Ajouter un triplet")
    add_p.add_argument("subject")
    add_p.add_argument("predicate")
    add_p.add_argument("object")
    add_p.add_argument("--confidence", type=float, default=1.0)

    # query
    query_p = subparsers.add_parser("query", help="Recherche sémantique")
    query_p.add_argument("query")
    query_p.add_argument("-n", type=int, default=5)

    # relations
    rel_p = subparsers.add_parser("relations", help="Relations d'une entité")
    rel_p.add_argument("entity")
    rel_p.add_argument("--direction", choices=["outgoing", "incoming", "both"], default="both")

    # path
    path_p = subparsers.add_parser("path", help="Chemin entre deux entités")
    path_p.add_argument("source")
    path_p.add_argument("target")

    # extract
    extract_p = subparsers.add_parser("extract", help="Extraire triplets d'un texte")
    extract_p.add_argument("text")

    # stats
    subparsers.add_parser("stats", help="Statistiques")

    # predicates
    subparsers.add_parser("predicates", help="Liste des types de relations")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    kg = KnowledgeGraph()

    if args.command == "add":
        triple_id = kg.add_triple(
            args.subject, args.predicate, args.object, args.confidence
        )
        print(f"Triplet ajouté: {triple_id}")
        print(f"  {args.subject} --[{args.predicate}]--> {args.object}")

    elif args.command == "query":
        results = kg.query_semantic(args.query, n_results=args.n)
        if not results:
            print("Aucun résultat.")
        else:
            print(f"Trouvé {len(results)} triplet(s):\n")
            for triple, score in results:
                print(f"[{score:.3f}] {triple.subject} --[{triple.predicate}]--> {triple.object}")

    elif args.command == "relations":
        triples = kg.get_relations(args.entity, args.direction)
        print(f"Relations de '{args.entity}' ({args.direction}):\n")
        for triple in triples:
            print(f"  {triple.subject} --[{triple.predicate}]--> {triple.object}")

    elif args.command == "path":
        path = kg.get_path(args.source, args.target)
        if path is None:
            print(f"Aucun chemin trouvé entre '{args.source}' et '{args.target}'")
        elif not path:
            print("Les entités sont identiques.")
        else:
            print(f"Chemin trouvé ({len(path)} étapes):\n")
            print(f"  {args.source}")
            for triple in path:
                print(f"    --[{triple.predicate}]-->")
                print(f"  {triple.object}")

    elif args.command == "extract":
        created = kg.extract_triples_from_text(args.text)
        print(f"Extrait {len(created)} triplet(s)")

    elif args.command == "stats":
        stats = kg.get_stats()
        print("=== Graphe de Connaissances ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")

    elif args.command == "predicates":
        print("Types de relations disponibles:\n")
        for pred, desc in KnowledgeGraph.RELATION_TYPES.items():
            print(f"  {pred}: {desc}")
