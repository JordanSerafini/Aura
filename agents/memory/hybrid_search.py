#!/home/tinkerbell/.aura/venv/bin/python3
"""
AURA Hybrid Search v1.0 - Recherche BM25 + Vector combinée
Pattern: Fusion de scores BM25 (sparse) + Embeddings (dense)
Team: core (memory)

Sources:
- RAG Evolution 2025-2026 (ragflow.io)
- Hybrid Search Best Practices (Anthropic, Pinecone)
"""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HybridSearchResult:
    """Résultat de recherche hybride."""
    id: str
    content: str
    bm25_score: float
    vector_score: float
    combined_score: float
    metadata: dict


class BM25:
    """
    BM25 (Okapi BM25) pour recherche lexicale sparse.
    Implémentation optimisée sans dépendances externes.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus: list[list[str]] = []
        self.doc_lengths: list[int] = []
        self.avgdl: float = 0.0
        self.df: dict[str, int] = {}  # document frequency
        self.idf: dict[str, float] = {}  # inverse document frequency
        self.doc_ids: list[str] = []
        self.doc_contents: list[str] = []

    def tokenize(self, text: str) -> list[str]:
        """Tokenize et normalise un texte."""
        text = text.lower()
        # Simple tokenization: mots alphanumériques
        tokens = re.findall(r'\b[a-zàâäéèêëïîôùûüç0-9]+\b', text)
        return tokens

    def fit(self, documents: list[tuple[str, str]]) -> None:
        """
        Index les documents.

        Args:
            documents: Liste de (doc_id, content)
        """
        self.corpus = []
        self.doc_lengths = []
        self.doc_ids = []
        self.doc_contents = []
        self.df = {}

        for doc_id, content in documents:
            tokens = self.tokenize(content)
            self.corpus.append(tokens)
            self.doc_lengths.append(len(tokens))
            self.doc_ids.append(doc_id)
            self.doc_contents.append(content)

            # Calcul document frequency
            seen = set()
            for token in tokens:
                if token not in seen:
                    self.df[token] = self.df.get(token, 0) + 1
                    seen.add(token)

        # Calcul avgdl et IDF
        if self.doc_lengths:
            self.avgdl = sum(self.doc_lengths) / len(self.doc_lengths)

        n = len(self.corpus)
        for term, df_val in self.df.items():
            # IDF avec smoothing
            self.idf[term] = math.log((n - df_val + 0.5) / (df_val + 0.5) + 1)

    def score(self, query: str, doc_idx: int) -> float:
        """Calcule le score BM25 pour un document."""
        query_tokens = self.tokenize(query)
        doc_tokens = self.corpus[doc_idx]
        doc_len = self.doc_lengths[doc_idx]

        # Fréquence des termes dans le document
        tf = Counter(doc_tokens)

        score = 0.0
        for term in query_tokens:
            if term not in tf:
                continue

            term_freq = tf[term]
            idf = self.idf.get(term, 0.0)

            # Formule BM25
            numerator = term_freq * (self.k1 + 1)
            denominator = term_freq + self.k1 * (
                1 - self.b + self.b * doc_len / self.avgdl
            )
            score += idf * (numerator / denominator)

        return score

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, str, float]]:
        """
        Recherche BM25.

        Returns:
            Liste de (doc_id, content, score)
        """
        scores = []
        for idx in range(len(self.corpus)):
            score = self.score(query, idx)
            if score > 0:
                scores.append((self.doc_ids[idx], self.doc_contents[idx], score))

        # Trier par score décroissant
        scores.sort(key=lambda x: x[2], reverse=True)
        return scores[:top_k]


class HybridSearchEngine:
    """
    Moteur de recherche hybride combinant BM25 et recherche vectorielle.
    Pattern: Reciprocal Rank Fusion (RRF) ou weighted combination.
    """

    def __init__(
        self,
        bm25_weight: float = 0.4,
        vector_weight: float = 0.6,
        use_chroma: bool = True
    ):
        """
        Args:
            bm25_weight: Poids pour BM25 (sparse)
            vector_weight: Poids pour vector search (dense)
            use_chroma: Utiliser ChromaDB pour les embeddings
        """
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.use_chroma = use_chroma

        self.bm25 = BM25()
        self.chroma_collection = None
        self.documents: dict[str, str] = {}  # id -> content
        self.metadata: dict[str, dict] = {}  # id -> metadata

        if use_chroma:
            self._init_chroma()

    def _init_chroma(self) -> None:
        """Initialise ChromaDB si disponible."""
        try:
            import chromadb
            from chromadb.config import Settings

            persist_dir = Path.home() / ".aura" / "memory" / "hybrid_chroma"
            persist_dir.mkdir(parents=True, exist_ok=True)

            self.chroma_client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )
            self.chroma_collection = self.chroma_client.get_or_create_collection(
                name="hybrid_search",
                metadata={"hnsw:space": "cosine"}
            )
        except ImportError:
            print("Warning: ChromaDB not available, using BM25 only")
            self.use_chroma = False

    def index(
        self,
        doc_id: str,
        content: str,
        metadata: dict | None = None
    ) -> None:
        """
        Indexe un document pour la recherche hybride.

        Args:
            doc_id: Identifiant unique
            content: Contenu textuel
            metadata: Métadonnées optionnelles
        """
        self.documents[doc_id] = content
        self.metadata[doc_id] = metadata or {}

        # Index ChromaDB (embeddings automatiques)
        if self.chroma_collection is not None:
            self.chroma_collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[metadata or {}]
            )

    def rebuild_bm25(self) -> None:
        """Reconstruit l'index BM25."""
        docs = [(doc_id, content) for doc_id, content in self.documents.items()]
        self.bm25.fit(docs)

    def index_batch(
        self,
        documents: list[tuple[str, str, dict | None]]
    ) -> int:
        """
        Indexe un lot de documents.

        Args:
            documents: Liste de (doc_id, content, metadata)

        Returns:
            Nombre de documents indexés
        """
        for doc_id, content, metadata in documents:
            self.documents[doc_id] = content
            self.metadata[doc_id] = metadata or {}

        # Batch pour ChromaDB
        if self.chroma_collection is not None:
            ids = [d[0] for d in documents]
            contents = [d[1] for d in documents]
            metas = [d[2] or {} for d in documents]

            self.chroma_collection.upsert(
                ids=ids,
                documents=contents,
                metadatas=metas
            )

        # Reconstruire BM25
        self.rebuild_bm25()

        return len(documents)

    def _normalize_scores(self, scores: list[float]) -> list[float]:
        """Normalise les scores entre 0 et 1."""
        if not scores:
            return []
        min_s = min(scores)
        max_s = max(scores)
        if max_s == min_s:
            return [1.0] * len(scores)
        return [(s - min_s) / (max_s - min_s) for s in scores]

    def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.0
    ) -> list[HybridSearchResult]:
        """
        Recherche hybride combinant BM25 et embeddings.

        Args:
            query: Requête de recherche
            top_k: Nombre de résultats
            min_score: Score minimum

        Returns:
            Liste de HybridSearchResult triés par score combiné
        """
        # Résultats BM25
        bm25_results = self.bm25.search(query, top_k=top_k * 2)
        bm25_scores = {doc_id: score for doc_id, _, score in bm25_results}

        # Résultats vectoriels
        vector_scores: dict[str, float] = {}
        if self.chroma_collection is not None:
            try:
                vector_results = self.chroma_collection.query(
                    query_texts=[query],
                    n_results=top_k * 2
                )
                if vector_results["ids"] and vector_results["distances"]:
                    for doc_id, dist in zip(
                        vector_results["ids"][0],
                        vector_results["distances"][0]
                    ):
                        # Convertir distance cosine en similarité
                        vector_scores[doc_id] = 1 - dist
            except Exception:
                pass

        # Fusionner les résultats
        all_ids = set(bm25_scores.keys()) | set(vector_scores.keys())

        # Normaliser les scores
        bm25_vals = list(bm25_scores.values()) if bm25_scores else [0]
        vector_vals = list(vector_scores.values()) if vector_scores else [0]

        bm25_max = max(bm25_vals) if bm25_vals else 1
        vector_max = max(vector_vals) if vector_vals else 1

        results = []
        for doc_id in all_ids:
            bm25_s = bm25_scores.get(doc_id, 0) / bm25_max if bm25_max > 0 else 0
            vector_s = vector_scores.get(doc_id, 0) / vector_max if vector_max > 0 else 0

            # Score combiné pondéré
            combined = (
                self.bm25_weight * bm25_s +
                self.vector_weight * vector_s
            )

            if combined >= min_score:
                results.append(HybridSearchResult(
                    id=doc_id,
                    content=self.documents.get(doc_id, ""),
                    bm25_score=bm25_s,
                    vector_score=vector_s,
                    combined_score=combined,
                    metadata=self.metadata.get(doc_id, {})
                ))

        # Trier par score combiné
        results.sort(key=lambda x: x.combined_score, reverse=True)

        return results[:top_k]

    def get_stats(self) -> dict:
        """Retourne les statistiques de l'index."""
        stats = {
            "total_documents": len(self.documents),
            "bm25_vocabulary_size": len(self.bm25.df),
            "bm25_avgdl": self.bm25.avgdl,
            "weights": {
                "bm25": self.bm25_weight,
                "vector": self.vector_weight
            },
            "chroma_enabled": self.chroma_collection is not None
        }

        if self.chroma_collection is not None:
            stats["chroma_count"] = self.chroma_collection.count()

        return stats

    def save_state(self, path: Path) -> None:
        """Sauvegarde l'état de l'index."""
        state = {
            "documents": self.documents,
            "metadata": self.metadata,
            "bm25_weight": self.bm25_weight,
            "vector_weight": self.vector_weight
        }
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    def load_state(self, path: Path) -> None:
        """Charge l'état de l'index."""
        if not path.exists():
            return

        state = json.loads(path.read_text())
        self.documents = state.get("documents", {})
        self.metadata = state.get("metadata", {})
        self.bm25_weight = state.get("bm25_weight", 0.4)
        self.vector_weight = state.get("vector_weight", 0.6)

        # Reconstruire BM25
        self.rebuild_bm25()


# Singleton pour réutilisation
_hybrid_engine: HybridSearchEngine | None = None


def get_hybrid_engine() -> HybridSearchEngine:
    """Retourne l'instance singleton du moteur hybride."""
    global _hybrid_engine
    if _hybrid_engine is None:
        _hybrid_engine = HybridSearchEngine()
    return _hybrid_engine


# CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AURA Hybrid Search")
    subparsers = parser.add_subparsers(dest="command")

    # search
    search_p = subparsers.add_parser("search", help="Recherche hybride")
    search_p.add_argument("query")
    search_p.add_argument("-n", type=int, default=5)

    # index
    index_p = subparsers.add_parser("index", help="Indexer un texte")
    index_p.add_argument("id")
    index_p.add_argument("content")

    # stats
    subparsers.add_parser("stats", help="Statistiques")

    # demo
    subparsers.add_parser("demo", help="Démonstration")

    args = parser.parse_args()

    engine = get_hybrid_engine()

    if args.command == "search":
        results = engine.search(args.query, top_k=args.n)
        for r in results:
            print(f"\n[{r.id}] Score: {r.combined_score:.3f}")
            print(f"  BM25: {r.bm25_score:.3f} | Vector: {r.vector_score:.3f}")
            print(f"  {r.content[:100]}...")

    elif args.command == "index":
        engine.index(args.id, args.content)
        engine.rebuild_bm25()
        print(f"Indexed: {args.id}")

    elif args.command == "stats":
        stats = engine.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.command == "demo":
        # Démo avec quelques documents
        demo_docs = [
            ("doc1", "Python est un langage de programmation versatile", {}),
            ("doc2", "JavaScript est utilisé pour le développement web", {}),
            ("doc3", "Les bases de données SQL stockent des données structurées", {}),
            ("doc4", "Le machine learning permet de créer des modèles prédictifs", {}),
            ("doc5", "Docker facilite le déploiement d'applications", {}),
        ]

        engine.index_batch(demo_docs)
        print(f"Indexé {len(demo_docs)} documents\n")

        queries = ["langage programmation", "web development", "données"]
        for q in queries:
            print(f"Query: '{q}'")
            results = engine.search(q, top_k=3)
            for r in results:
                print(f"  [{r.combined_score:.3f}] {r.content[:50]}...")
            print()

    else:
        parser.print_help()
