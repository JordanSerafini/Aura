#!/home/tinkerbell/.aura/venv/bin/python3
"""
AURA Temporal Graph v1.0 - Graphe de connaissances bi-temporel
Pattern Graphiti/Zep: Tracking temporel des faits avec valid_time et transaction_time

Team: core (memory)

Features:
- Bi-temporal: valid_time (quand le fait est vrai) + transaction_time (quand enregistré)
- Versioning des triplets (historique des modifications)
- Decay temporel pour scoring
- Requêtes point-in-time

Sources:
- Zep/Graphiti (github.com/getzep/graphiti)
- Temporal Databases (IEEE)
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class TemporalTriple:
    """Triplet de connaissance avec métadonnées temporelles."""
    id: str
    subject: str
    predicate: str
    object: str
    confidence: float

    # Bi-temporal
    valid_from: datetime  # Quand le fait devient vrai
    valid_to: datetime | None  # Quand le fait cesse d'être vrai (None = toujours vrai)
    transaction_time: datetime  # Quand enregistré dans le système

    # Métadonnées
    source: str = ""
    version: int = 1
    supersedes: str | None = None  # ID du triplet remplacé
    metadata: dict = field(default_factory=dict)

    def is_valid_at(self, point_in_time: datetime) -> bool:
        """Vérifie si le triplet est valide à un moment donné."""
        if point_in_time < self.valid_from:
            return False
        if self.valid_to is not None and point_in_time > self.valid_to:
            return False
        return True

    def is_current(self) -> bool:
        """Vérifie si le triplet est actuellement valide."""
        return self.is_valid_at(datetime.now())

    def age_hours(self) -> float:
        """Âge en heures depuis la création."""
        delta = datetime.now() - self.transaction_time
        return delta.total_seconds() / 3600

    def to_dict(self) -> dict:
        """Sérialise le triplet."""
        return {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "transaction_time": self.transaction_time.isoformat(),
            "source": self.source,
            "version": self.version,
            "supersedes": self.supersedes,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TemporalTriple":
        """Désérialise un triplet."""
        return cls(
            id=data["id"],
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            confidence=data.get("confidence", 1.0),
            valid_from=datetime.fromisoformat(data["valid_from"]),
            valid_to=datetime.fromisoformat(data["valid_to"]) if data.get("valid_to") else None,
            transaction_time=datetime.fromisoformat(data["transaction_time"]),
            source=data.get("source", ""),
            version=data.get("version", 1),
            supersedes=data.get("supersedes"),
            metadata=data.get("metadata", {})
        )


class TemporalGraph:
    """
    Graphe de connaissances bi-temporel avec versioning.
    """

    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or Path.home() / ".aura" / "memory" / "temporal_graph"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.triples_file = self.storage_path / "triples.jsonl"
        self.index_file = self.storage_path / "index.json"

        # Index en mémoire
        self.triples: dict[str, TemporalTriple] = {}
        self.subject_index: dict[str, list[str]] = {}
        self.predicate_index: dict[str, list[str]] = {}
        self.object_index: dict[str, list[str]] = {}

        self._load()

    def _load(self) -> None:
        """Charge les triplets depuis le stockage."""
        if self.triples_file.exists():
            with open(self.triples_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            triple = TemporalTriple.from_dict(data)
                            self._index_triple(triple)
                        except Exception:
                            continue

    def _index_triple(self, triple: TemporalTriple) -> None:
        """Ajoute un triplet aux index."""
        self.triples[triple.id] = triple

        # Index par sujet
        if triple.subject not in self.subject_index:
            self.subject_index[triple.subject] = []
        self.subject_index[triple.subject].append(triple.id)

        # Index par prédicat
        if triple.predicate not in self.predicate_index:
            self.predicate_index[triple.predicate] = []
        self.predicate_index[triple.predicate].append(triple.id)

        # Index par objet
        if triple.object not in self.object_index:
            self.object_index[triple.object] = []
        self.object_index[triple.object].append(triple.id)

    def _save_triple(self, triple: TemporalTriple) -> None:
        """Sauvegarde un triplet."""
        with open(self.triples_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(triple.to_dict(), ensure_ascii=False) + "\n")

    def add(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        source: str = "",
        metadata: dict | None = None
    ) -> str:
        """
        Ajoute un nouveau triplet temporel.

        Args:
            subject: Sujet
            predicate: Prédicat/relation
            obj: Objet
            confidence: Niveau de confiance (0-1)
            valid_from: Début de validité (défaut: maintenant)
            valid_to: Fin de validité (None = toujours valide)
            source: Source de l'information
            metadata: Métadonnées additionnelles

        Returns:
            ID du triplet créé
        """
        now = datetime.now()

        triple = TemporalTriple(
            id=str(uuid.uuid4()),
            subject=subject,
            predicate=predicate,
            object=obj,
            confidence=confidence,
            valid_from=valid_from or now,
            valid_to=valid_to,
            transaction_time=now,
            source=source,
            version=1,
            metadata=metadata or {}
        )

        self._index_triple(triple)
        self._save_triple(triple)

        return triple.id

    def update(
        self,
        triple_id: str,
        new_object: str | None = None,
        new_confidence: float | None = None,
        valid_to: datetime | None = None
    ) -> str | None:
        """
        Met à jour un triplet (crée une nouvelle version).

        Args:
            triple_id: ID du triplet à mettre à jour
            new_object: Nouvel objet
            new_confidence: Nouvelle confiance
            valid_to: Nouvelle fin de validité

        Returns:
            ID de la nouvelle version ou None si non trouvé
        """
        if triple_id not in self.triples:
            return None

        old_triple = self.triples[triple_id]
        now = datetime.now()

        # Marquer l'ancien comme terminé
        old_triple.valid_to = now

        # Créer la nouvelle version
        new_triple = TemporalTriple(
            id=str(uuid.uuid4()),
            subject=old_triple.subject,
            predicate=old_triple.predicate,
            object=new_object if new_object is not None else old_triple.object,
            confidence=new_confidence if new_confidence is not None else old_triple.confidence,
            valid_from=now,
            valid_to=valid_to,
            transaction_time=now,
            source=old_triple.source,
            version=old_triple.version + 1,
            supersedes=triple_id,
            metadata=old_triple.metadata
        )

        self._index_triple(new_triple)
        self._save_triple(new_triple)

        return new_triple.id

    def invalidate(self, triple_id: str) -> bool:
        """
        Invalide un triplet (le marque comme terminé maintenant).

        Args:
            triple_id: ID du triplet

        Returns:
            True si invalidé
        """
        if triple_id not in self.triples:
            return False

        self.triples[triple_id].valid_to = datetime.now()
        return True

    def query_current(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None
    ) -> list[TemporalTriple]:
        """
        Requête sur les triplets actuellement valides.

        Args:
            subject: Filtrer par sujet
            predicate: Filtrer par prédicat
            obj: Filtrer par objet

        Returns:
            Liste des triplets correspondants
        """
        return self.query_at_time(datetime.now(), subject, predicate, obj)

    def query_at_time(
        self,
        point_in_time: datetime,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None
    ) -> list[TemporalTriple]:
        """
        Requête point-in-time.

        Args:
            point_in_time: Moment de référence
            subject: Filtrer par sujet
            predicate: Filtrer par prédicat
            obj: Filtrer par objet

        Returns:
            Liste des triplets valides à ce moment
        """
        candidates = set(self.triples.keys())

        # Filtrer par index
        if subject and subject in self.subject_index:
            candidates &= set(self.subject_index[subject])
        elif subject:
            candidates = set()

        if predicate and predicate in self.predicate_index:
            candidates &= set(self.predicate_index[predicate])
        elif predicate:
            candidates = set()

        if obj and obj in self.object_index:
            candidates &= set(self.object_index[obj])
        elif obj:
            candidates = set()

        # Filtrer par validité temporelle
        results = []
        for tid in candidates:
            triple = self.triples[tid]
            if triple.is_valid_at(point_in_time):
                results.append(triple)

        return results

    def get_history(self, subject: str, predicate: str) -> list[TemporalTriple]:
        """
        Récupère l'historique complet d'une relation.

        Args:
            subject: Sujet
            predicate: Prédicat

        Returns:
            Liste chronologique des versions
        """
        results = []

        for triple in self.triples.values():
            if triple.subject == subject and triple.predicate == predicate:
                results.append(triple)

        # Trier par valid_from
        results.sort(key=lambda t: t.valid_from)
        return results

    def get_entity_timeline(self, entity: str) -> list[dict]:
        """
        Récupère la timeline d'une entité (sujet ou objet).

        Args:
            entity: Nom de l'entité

        Returns:
            Timeline d'événements
        """
        events = []

        # Comme sujet
        if entity in self.subject_index:
            for tid in self.subject_index[entity]:
                triple = self.triples[tid]
                events.append({
                    "time": triple.valid_from,
                    "type": "fact_added",
                    "role": "subject",
                    "triple": triple.to_dict()
                })
                if triple.valid_to:
                    events.append({
                        "time": triple.valid_to,
                        "type": "fact_ended",
                        "role": "subject",
                        "triple": triple.to_dict()
                    })

        # Comme objet
        if entity in self.object_index:
            for tid in self.object_index[entity]:
                triple = self.triples[tid]
                events.append({
                    "time": triple.valid_from,
                    "type": "fact_added",
                    "role": "object",
                    "triple": triple.to_dict()
                })
                if triple.valid_to:
                    events.append({
                        "time": triple.valid_to,
                        "type": "fact_ended",
                        "role": "object",
                        "triple": triple.to_dict()
                    })

        # Trier par temps
        events.sort(key=lambda e: e["time"])
        return events

    def compute_decay_score(
        self,
        triple: TemporalTriple,
        decay_rate: float = 0.1
    ) -> float:
        """
        Calcule un score avec decay temporel.

        Args:
            triple: Le triplet
            decay_rate: Taux de décroissance par jour

        Returns:
            Score décroissant avec le temps
        """
        age_days = triple.age_hours() / 24
        decay = 1.0 / (1.0 + decay_rate * age_days)
        return triple.confidence * decay

    def search_with_decay(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        obj: str | None = None,
        decay_rate: float = 0.1,
        min_score: float = 0.0
    ) -> list[tuple[TemporalTriple, float]]:
        """
        Recherche avec scoring temporel.

        Returns:
            Liste de (triple, score) triés par score
        """
        current = self.query_current(subject, predicate, obj)

        scored = []
        for triple in current:
            score = self.compute_decay_score(triple, decay_rate)
            if score >= min_score:
                scored.append((triple, score))

        # Trier par score décroissant
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def get_stats(self) -> dict:
        """Retourne les statistiques du graphe."""
        current_triples = [t for t in self.triples.values() if t.is_current()]

        return {
            "total_triples": len(self.triples),
            "current_triples": len(current_triples),
            "unique_subjects": len(self.subject_index),
            "unique_predicates": len(self.predicate_index),
            "unique_objects": len(self.object_index),
            "avg_confidence": (
                sum(t.confidence for t in current_triples) / len(current_triples)
                if current_triples else 0
            )
        }


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AURA Temporal Graph")
    subparsers = parser.add_subparsers(dest="command")

    # add
    add_p = subparsers.add_parser("add", help="Ajouter un triplet")
    add_p.add_argument("subject")
    add_p.add_argument("predicate")
    add_p.add_argument("object")
    add_p.add_argument("--confidence", type=float, default=1.0)
    add_p.add_argument("--source", default="")

    # query
    query_p = subparsers.add_parser("query", help="Rechercher")
    query_p.add_argument("--subject", "-s")
    query_p.add_argument("--predicate", "-p")
    query_p.add_argument("--object", "-o")

    # history
    hist_p = subparsers.add_parser("history", help="Historique d'une relation")
    hist_p.add_argument("subject")
    hist_p.add_argument("predicate")

    # timeline
    time_p = subparsers.add_parser("timeline", help="Timeline d'une entité")
    time_p.add_argument("entity")

    # stats
    subparsers.add_parser("stats", help="Statistiques")

    # demo
    subparsers.add_parser("demo", help="Démonstration")

    args = parser.parse_args()

    graph = TemporalGraph()

    if args.command == "add":
        tid = graph.add(
            subject=args.subject,
            predicate=args.predicate,
            obj=args.object,
            confidence=args.confidence,
            source=args.source
        )
        print(f"Added: {tid}")
        print(f"  {args.subject} --[{args.predicate}]--> {args.object}")

    elif args.command == "query":
        results = graph.query_current(
            subject=args.subject,
            predicate=args.predicate,
            obj=args.object
        )
        print(f"Found {len(results)} triples:\n")
        for t in results:
            print(f"  [{t.id[:8]}] {t.subject} --[{t.predicate}]--> {t.object}")
            print(f"         confidence: {t.confidence}, valid_from: {t.valid_from}")

    elif args.command == "history":
        history = graph.get_history(args.subject, args.predicate)
        print(f"History of {args.subject} --[{args.predicate}]-->:\n")
        for t in history:
            status = "CURRENT" if t.is_current() else "ENDED"
            print(f"  v{t.version} [{status}] --> {t.object}")
            print(f"     valid: {t.valid_from} to {t.valid_to or 'now'}")

    elif args.command == "timeline":
        events = graph.get_entity_timeline(args.entity)
        print(f"Timeline of '{args.entity}':\n")
        for e in events:
            print(f"  [{e['time']}] {e['type']} as {e['role']}")

    elif args.command == "stats":
        stats = graph.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.command == "demo":
        # Démo avec des données temporelles
        print("=== Temporal Graph Demo ===\n")

        # Ajouter des faits
        graph.add("Aura", "runs_on", "Linux", source="config")
        graph.add("Aura", "version", "3.1", source="config")
        graph.add("Python", "is_a", "programming_language", source="knowledge")

        print("Added initial facts\n")

        # Simuler une mise à jour
        results = graph.query_current(subject="Aura", predicate="version")
        if results:
            old_id = results[0].id
            graph.update(old_id, new_object="3.2")
            print("Updated Aura version: 3.1 -> 3.2\n")

        # Afficher l'historique
        history = graph.get_history("Aura", "version")
        print("Version history:")
        for t in history:
            status = "CURRENT" if t.is_current() else "SUPERSEDED"
            print(f"  v{t.version}: {t.object} [{status}]")

        print("\nStats:", json.dumps(graph.get_stats(), indent=2))

    else:
        parser.print_help()
