#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Memory Manager v3.1 - Système de mémoire multi-niveaux
Architecture: Épisodique + Procédurale + Graphe de connaissances + RAG Documents

Point d'entrée principal pour toutes les opérations de mémoire.
"""

import argparse
import json
import os
import sys
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Import des nouveaux composants
sys.path.insert(0, str(Path(__file__).parent / "memory"))
try:
    from memory import (
        MemoryAPI, EpisodicMemory, ProceduralMemory,
        KnowledgeGraph, MemoryConsolidator, MEMORY_CONFIG
    )
    ADVANCED_MEMORY = True
except ImportError:
    ADVANCED_MEMORY = False

# Configuration optimisée (basée sur recherches 2025-2026)
MEMORY_DIR = Path.home() / ".aura" / "memory" / "chroma_db"
CHUNK_SIZE = 512  # Optimal selon recherches
CHUNK_OVERLAP = 100
MODEL_NAME = "all-MiniLM-L6-v2"  # 384 dimensions, rapide
TOP_K = 5

# Collections pour documents/notes (compatibilité avec ancienne version)
COLLECTIONS = {
    "documents": "Fichiers indexés (code, docs, etc.)",
    "conversations": "Historique des conversations",
    "notes": "Notes et informations sauvegardées"
}

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".go", ".rs", ".rb", ".php", ".sh", ".bash", ".zsh",
    ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
    ".html", ".css", ".scss", ".sql", ".xml", ".csv"
}


class MemoryManager:
    """
    Gestionnaire de mémoire unifié v3.1.
    Combine RAG documents avec mémoire épisodique, procédurale et graphe de connaissances.
    """

    def __init__(self):
        """Initialise le gestionnaire de mémoire."""
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        # ChromaDB pour documents (compatibilité)
        self.client = chromadb.PersistentClient(
            path=str(MEMORY_DIR),
            settings=Settings(anonymized_telemetry=False)
        )

        self._model = None
        self.collections = {}
        for name in COLLECTIONS.keys():
            self.collections[name] = self.client.get_or_create_collection(
                name=name,
                metadata={"description": COLLECTIONS[name]}
            )

        # Nouveau système de mémoire avancé
        self._api: MemoryAPI | None = None

    @property
    def model(self) -> SentenceTransformer:
        """Charge le modèle d'embedding à la demande."""
        if self._model is None:
            self._model = SentenceTransformer(MODEL_NAME)
        return self._model

    @property
    def api(self) -> 'MemoryAPI' | None:
        """Accès à l'API de mémoire avancée."""
        if self._api is None and ADVANCED_MEMORY:
            self._api = MemoryAPI()
        return self._api

    def _chunk_text(self, text: str) -> list[str]:
        """Découpe le texte en chunks optimisés (512 tokens)."""
        if len(text) <= CHUNK_SIZE:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - CHUNK_OVERLAP
        return chunks

    def _generate_id(self, content: str, source: str, index: int) -> str:
        """Génère un ID unique pour un chunk."""
        data = f"{source}:{index}:{content[:100]}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Génère les embeddings."""
        embeddings = self.model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    # === Fonctions RAG Documents (compatibilité) ===

    def index_file(self, file_path: Path) -> int:
        """Indexe un fichier dans la collection documents."""
        if not file_path.exists():
            raise FileNotFoundError(f"Fichier non trouvé: {file_path}")

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return 0

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"Erreur lecture {file_path}: {e}", file=sys.stderr)
            return 0

        if not content.strip():
            return 0

        chunks = self._chunk_text(content)
        collection = self.collections["documents"]

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            doc_id = self._generate_id(chunk, str(file_path), i)
            ids.append(doc_id)
            documents.append(chunk)
            metadatas.append({
                "source": str(file_path.absolute()),
                "filename": file_path.name,
                "extension": file_path.suffix,
                "category": "document",
                "chunk_index": i,
                "total_chunks": len(chunks),
                "indexed_at": datetime.now().isoformat()
            })

        embeddings = self._get_embeddings(documents)

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

        return len(chunks)

    def index_directory(self, dir_path: Path, recursive: bool = True) -> dict[str, int]:
        """Indexe un dossier."""
        if not dir_path.exists():
            raise FileNotFoundError(f"Dossier non trouvé: {dir_path}")

        stats = {"files": 0, "chunks": 0, "errors": 0}

        pattern = "**/*" if recursive else "*"
        for file_path in dir_path.glob(pattern):
            if file_path.is_file():
                try:
                    chunks = self.index_file(file_path)
                    if chunks > 0:
                        stats["files"] += 1
                        stats["chunks"] += chunks
                        print(f"  Indexé: {file_path.name} ({chunks} chunks)")
                except Exception as e:
                    stats["errors"] += 1
                    print(f"  Erreur: {file_path.name} - {e}", file=sys.stderr)

        return stats

    def search(self, query: str, collection_name: str | None = None, n_results: int = TOP_K) -> list[dict[str, Any]]:
        """Recherche dans les documents indexés."""
        query_embedding = self._get_embeddings([query])[0]
        results = []

        collections_to_search = [collection_name] if collection_name else COLLECTIONS.keys()

        for coll_name in collections_to_search:
            if coll_name not in self.collections:
                continue

            collection = self.collections[coll_name]
            if collection.count() == 0:
                continue

            search_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, collection.count())
            )

            for i, doc_id in enumerate(search_results["ids"][0]):
                results.append({
                    "id": doc_id,
                    "collection": coll_name,
                    "content": search_results["documents"][0][i],
                    "metadata": search_results["metadatas"][0][i],
                    "distance": search_results["distances"][0][i] if search_results["distances"] else None
                })

        results.sort(key=lambda x: x["distance"] if x["distance"] else float("inf"))
        return results[:n_results]

    def remember(self, text: str, category: str = "note") -> str:
        """Sauvegarde une information."""
        collection_map = {
            "conversation": "conversations",
            "note": "notes",
            "fact": "notes"
        }

        coll_name = collection_map.get(category, "notes")
        collection = self.collections[coll_name]

        doc_id = self._generate_id(text, category, 0)
        embedding = self._get_embeddings([text])[0]

        collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "source": "user_input",
                "category": category,
                "chunk_index": 0,
                "created_at": datetime.now().isoformat()
            }]
        )

        return doc_id

    def recall(self, context: str, n_results: int = TOP_K) -> list[dict[str, Any]]:
        """Rappelle le contexte pertinent."""
        return self.search(context, n_results=n_results)

    def forget(self, doc_id: str | None = None, older_than: str | None = None) -> int:
        """Supprime des entrées."""
        deleted = 0

        if doc_id:
            for collection in self.collections.values():
                try:
                    collection.delete(ids=[doc_id])
                    deleted += 1
                except Exception:
                    pass

        elif older_than:
            value = int(older_than[:-1])
            unit = older_than[-1]

            if unit == "d":
                delta = timedelta(days=value)
            elif unit == "h":
                delta = timedelta(hours=value)
            else:
                raise ValueError(f"Unité non supportée: {unit}")

            cutoff = datetime.now() - delta
            cutoff_iso = cutoff.isoformat()

            for collection in self.collections.values():
                all_docs = collection.get()
                ids_to_delete = []

                for i, metadata in enumerate(all_docs["metadatas"]):
                    date_field = metadata.get("indexed_at") or metadata.get("created_at")
                    if date_field and date_field < cutoff_iso:
                        ids_to_delete.append(all_docs["ids"][i])

                if ids_to_delete:
                    collection.delete(ids=ids_to_delete)
                    deleted += len(ids_to_delete)

        return deleted

    # === Nouvelles fonctions v3.1 ===

    def record_episode(
        self,
        context: str,
        action: str,
        outcome: str,
        thought_process: str = "",
        importance: float = 0.5,
        valence: float = 0.0
    ) -> str | None:
        """Enregistre un épisode dans la mémoire épisodique."""
        if not self.api:
            print("Mémoire avancée non disponible", file=sys.stderr)
            return None

        result = self.api.record_episode(
            context=context,
            action=action,
            outcome=outcome,
            thought_process=thought_process,
            importance=importance,
            valence=valence
        )
        return result.get("episode_id")

    def recall_episodes(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Rappelle des épisodes pertinents."""
        if not self.api:
            return []
        result = self.api.recall_episodes(query, n_results)
        return result.get("episodes", [])

    def find_skills(self, context: str, n_results: int = 3) -> list[dict[str, Any]]:
        """Trouve les skills applicables."""
        if not self.api:
            return []
        result = self.api.find_skills(context, n_results)
        return result.get("skills", [])

    def add_knowledge(self, subject: str, predicate: str, obj: str) -> str | None:
        """Ajoute un triplet de connaissance."""
        if not self.api:
            return None
        result = self.api.add_knowledge(subject, predicate, obj)
        return result.get("triple_id")

    def query_knowledge(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Recherche dans le graphe de connaissances."""
        if not self.api:
            return []
        result = self.api.query_knowledge(query, n_results)
        return result.get("triples", [])

    def consolidate(self, dry_run: bool = False) -> dict[str, Any]:
        """Lance une consolidation de la mémoire."""
        if not self.api:
            return {"error": "Mémoire avancée non disponible"}
        return self.api.consolidate(dry_run=dry_run)

    def unified_search(self, query: str, n_results: int = 5) -> dict[str, Any]:
        """Recherche unifiée dans tous les types de mémoire."""
        results = {
            "documents": self.search(query, n_results=n_results),
            "episodes": [],
            "skills": [],
            "knowledge": []
        }

        if self.api:
            results["episodes"] = self.recall_episodes(query, n_results)
            results["skills"] = self.find_skills(query, n_results)
            results["knowledge"] = self.query_knowledge(query, n_results)

        return results

    def get_stats(self) -> dict[str, Any]:
        """Statistiques complètes."""
        stats = {
            "version": "3.1.0",
            "chunk_size": CHUNK_SIZE,
            "model": MODEL_NAME,
            "storage_path": str(MEMORY_DIR),
            "total_documents": 0,
            "collections": {}
        }

        # Stats documents
        for name, collection in self.collections.items():
            count = collection.count()
            stats["collections"][name] = {
                "count": count,
                "description": COLLECTIONS[name]
            }
            stats["total_documents"] += count

        # Taille stockage
        total_size = sum(f.stat().st_size for f in MEMORY_DIR.rglob("*") if f.is_file())
        stats["storage_size_mb"] = round(total_size / (1024 * 1024), 2)

        # Stats avancées
        if self.api:
            advanced_stats = self.api.get_stats()
            stats["episodic"] = advanced_stats.get("episodic", {})
            stats["procedural"] = advanced_stats.get("procedural", {})
            stats["knowledge"] = advanced_stats.get("knowledge", {})
            stats["advanced_memory"] = True
        else:
            stats["advanced_memory"] = False

        return stats


def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(
        description="Aura Memory Manager v3.1 - Système de mémoire multi-niveaux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
=== Commandes RAG (documents) ===
  %(prog)s index ~/projects/myapp
  %(prog)s search "comment implémenter X"
  %(prog)s remember "Note importante" --category note
  %(prog)s recall "contexte de travail"
  %(prog)s forget --older-than 30d

=== Commandes Mémoire Avancée v3.1 ===
  %(prog)s episode --context "..." --action "..." --outcome "..."
  %(prog)s episodes "requête de recherche"
  %(prog)s skills "contexte actuel"
  %(prog)s knowledge add "Python" "is_a" "language"
  %(prog)s knowledge query "Python"
  %(prog)s consolidate [--dry-run]
  %(prog)s unified "recherche globale"
  %(prog)s stats
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    # === Commandes RAG ===
    index_parser = subparsers.add_parser("index", help="Indexer un fichier ou dossier")
    index_parser.add_argument("path", type=str)
    index_parser.add_argument("--no-recursive", action="store_true")

    search_parser = subparsers.add_parser("search", help="Rechercher dans les documents")
    search_parser.add_argument("query", type=str)
    search_parser.add_argument("-n", "--num", type=int, default=TOP_K)
    search_parser.add_argument("-c", "--collection", type=str, choices=list(COLLECTIONS.keys()))

    remember_parser = subparsers.add_parser("remember", help="Sauvegarder une information")
    remember_parser.add_argument("text", type=str)
    remember_parser.add_argument("--category", type=str, choices=["conversation", "note", "fact"], default="note")

    recall_parser = subparsers.add_parser("recall", help="Rappeler le contexte")
    recall_parser.add_argument("context", type=str)
    recall_parser.add_argument("-n", "--num", type=int, default=TOP_K)

    forget_parser = subparsers.add_parser("forget", help="Supprimer des entrées")
    forget_group = forget_parser.add_mutually_exclusive_group(required=True)
    forget_group.add_argument("--id", type=str)
    forget_group.add_argument("--older-than", type=str)

    # === Commandes Mémoire Avancée ===
    episode_parser = subparsers.add_parser("episode", help="Enregistrer un épisode")
    episode_parser.add_argument("--context", required=True)
    episode_parser.add_argument("--action", required=True)
    episode_parser.add_argument("--outcome", required=True)
    episode_parser.add_argument("--thought", default="")
    episode_parser.add_argument("--importance", type=float, default=0.5)
    episode_parser.add_argument("--valence", type=float, default=0.0)

    episodes_parser = subparsers.add_parser("episodes", help="Rechercher des épisodes")
    episodes_parser.add_argument("query", type=str)
    episodes_parser.add_argument("-n", type=int, default=5)

    skills_parser = subparsers.add_parser("skills", help="Trouver des skills applicables")
    skills_parser.add_argument("context", type=str)
    skills_parser.add_argument("-n", type=int, default=3)

    knowledge_parser = subparsers.add_parser("knowledge", help="Graphe de connaissances")
    knowledge_sub = knowledge_parser.add_subparsers(dest="kg_command")
    kg_add = knowledge_sub.add_parser("add", help="Ajouter un triplet")
    kg_add.add_argument("subject")
    kg_add.add_argument("predicate")
    kg_add.add_argument("object")
    kg_query = knowledge_sub.add_parser("query", help="Rechercher")
    kg_query.add_argument("query")
    kg_query.add_argument("-n", type=int, default=5)

    consolidate_parser = subparsers.add_parser("consolidate", help="Consolider la mémoire")
    consolidate_parser.add_argument("--dry-run", action="store_true")

    unified_parser = subparsers.add_parser("unified", help="Recherche unifiée")
    unified_parser.add_argument("query", type=str)
    unified_parser.add_argument("-n", type=int, default=5)

    subparsers.add_parser("stats", help="Statistiques complètes")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        manager = MemoryManager()

        # === RAG ===
        if args.command == "index":
            path = Path(args.path).expanduser().resolve()
            print(f"Indexation de: {path}")

            if path.is_file():
                chunks = manager.index_file(path)
                print(f"Fichier indexé: {chunks} chunks")
            elif path.is_dir():
                stats = manager.index_directory(path, recursive=not args.no_recursive)
                print(f"\nTerminé: {stats['files']} fichiers, {stats['chunks']} chunks, {stats['errors']} erreurs")
            else:
                print(f"Erreur: {path} n'existe pas", file=sys.stderr)
                sys.exit(1)

        elif args.command == "search":
            results = manager.search(args.query, collection_name=args.collection, n_results=args.num)
            if not results:
                print("Aucun résultat trouvé.")
            else:
                print(f"Trouvé {len(results)} résultat(s):\n")
                for i, r in enumerate(results, 1):
                    print(f"--- Résultat {i} [{r['collection']}] (distance: {r['distance']:.4f}) ---")
                    print(f"Source: {r['metadata'].get('source', 'N/A')}")
                    content = r["content"][:300] + "..." if len(r["content"]) > 300 else r["content"]
                    print(f"Contenu:\n{content}\n")

        elif args.command == "remember":
            doc_id = manager.remember(args.text, category=args.category)
            print(f"Information sauvegardée (ID: {doc_id})")

        elif args.command == "recall":
            results = manager.recall(args.context, n_results=args.num)
            if not results:
                print("Aucun contexte pertinent trouvé.")
            else:
                print(f"Contexte rappelé ({len(results)} éléments):\n")
                for i, r in enumerate(results, 1):
                    print(f"[{i}] {r['collection']} - {r['metadata'].get('source', 'N/A')}")
                    content = r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"]
                    print(f"    {content}\n")

        elif args.command == "forget":
            if args.id:
                deleted = manager.forget(doc_id=args.id)
                print(f"Document supprimé: {args.id}" if deleted else "Document non trouvé")
            else:
                deleted = manager.forget(older_than=args.older_than)
                print(f"Supprimé: {deleted} document(s)")

        # === Mémoire Avancée ===
        elif args.command == "episode":
            ep_id = manager.record_episode(
                context=args.context,
                action=args.action,
                outcome=args.outcome,
                thought_process=args.thought,
                importance=args.importance,
                valence=args.valence
            )
            if ep_id:
                print(f"Épisode enregistré: {ep_id}")
            else:
                print("Erreur: mémoire avancée non disponible")

        elif args.command == "episodes":
            episodes = manager.recall_episodes(args.query, n_results=args.n)
            if not episodes:
                print("Aucun épisode trouvé.")
            else:
                print(f"Trouvé {len(episodes)} épisode(s):\n")
                for ep in episodes:
                    print(f"[{ep['id']}] Score: {ep['score']:.3f}")
                    print(f"  Contexte: {ep['context'][:80]}...")
                    print(f"  Action: {ep['action'][:80]}...")
                    print()

        elif args.command == "skills":
            skills = manager.find_skills(args.context, n_results=args.n)
            if not skills:
                print("Aucun skill applicable trouvé.")
            else:
                print(f"Trouvé {len(skills)} skill(s):\n")
                for sk in skills:
                    print(f"[{sk['name']}] Score: {sk['score']:.3f}")
                    print(f"  Pattern: {sk['pattern'][:80]}...")
                    print(f"  Success rate: {sk['success_rate']:.1%}")
                    print()

        elif args.command == "knowledge":
            if args.kg_command == "add":
                triple_id = manager.add_knowledge(args.subject, args.predicate, args.object)
                if triple_id:
                    print(f"Triplet ajouté: {triple_id}")
                    print(f"  {args.subject} --[{args.predicate}]--> {args.object}")
                else:
                    print("Erreur: mémoire avancée non disponible")
            elif args.kg_command == "query":
                triples = manager.query_knowledge(args.query, n_results=args.n)
                if not triples:
                    print("Aucun triplet trouvé.")
                else:
                    print(f"Trouvé {len(triples)} triplet(s):\n")
                    for t in triples:
                        print(f"  {t['subject']} --[{t['predicate']}]--> {t['object']}")
            else:
                knowledge_parser.print_help()

        elif args.command == "consolidate":
            result = manager.consolidate(dry_run=args.dry_run)
            print("=== Consolidation ===")
            print(json.dumps(result, indent=2))

        elif args.command == "unified":
            results = manager.unified_search(args.query, n_results=args.n)
            print("=== Recherche Unifiée ===\n")

            print(f"Documents: {len(results['documents'])}")
            for doc in results['documents'][:3]:
                print(f"  - {doc['metadata'].get('filename', 'N/A')}")

            print(f"\nÉpisodes: {len(results['episodes'])}")
            for ep in results['episodes'][:3]:
                print(f"  - [{ep['id']}] {ep['context'][:50]}...")

            print(f"\nSkills: {len(results['skills'])}")
            for sk in results['skills'][:3]:
                print(f"  - {sk['name']}")

            print(f"\nConnaissances: {len(results['knowledge'])}")
            for t in results['knowledge'][:3]:
                print(f"  - {t['subject']} -> {t['predicate']} -> {t['object']}")

        elif args.command == "stats":
            stats = manager.get_stats()
            print("=== Statistiques Mémoire Aura v3.1 ===\n")
            print(f"Version: {stats['version']}")
            print(f"Chunk size: {stats['chunk_size']} (optimisé)")
            print(f"Modèle: {stats['model']}")
            print(f"Stockage: {stats['storage_path']}")
            print(f"Taille: {stats['storage_size_mb']} MB")
            print(f"Mémoire avancée: {'Oui' if stats['advanced_memory'] else 'Non'}")

            print(f"\nDocuments: {stats['total_documents']}")
            for name, info in stats["collections"].items():
                print(f"  - {name}: {info['count']}")

            if stats.get("episodic"):
                print(f"\nÉpisodique: {stats['episodic'].get('total_episodes', 0)} épisodes")
            if stats.get("procedural"):
                print(f"Procédurale: {stats['procedural'].get('total_skills', 0)} skills")
            if stats.get("knowledge"):
                print(f"Graphe: {stats['knowledge'].get('total_triples', 0)} triplets")

    except KeyboardInterrupt:
        print("\nOpération annulée.")
        sys.exit(130)
    except Exception as e:
        print(f"Erreur: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
