#!/home/tinkerbell/.aura/venv/bin/python3
"""
Tests du système de mémoire Aura v3.1
Vérifie le bon fonctionnement de tous les composants.
"""

import sys
import tempfile
from pathlib import Path

# Tests sans assertions pour exécution rapide
def test_memory_types():
    """Test des types de mémoire."""
    print("Test: memory_types...")

    from memory_types import (
        MemoryType, Episode, Skill, KnowledgeTriple,
        MemoryScore, calculate_recency_score
    )

    # Test Episode
    episode = Episode(
        id="",
        timestamp="2026-01-15T10:00:00",
        context="Utilisateur demande une recherche",
        action="Recherche dans les fichiers",
        outcome="Trouvé 5 fichiers",
        thought_process="J'utilise grep pour chercher",
        entities=["fichiers", "grep"],
        importance=0.7
    )
    assert episode.id.startswith("ep_"), "Episode ID should start with ep_"
    print(f"  Episode créé: {episode.id}")

    # Test Skill
    skill = Skill(
        id="",
        name="recherche_fichiers",
        description="Recherche dans les fichiers",
        pattern="grep -r",
        trigger_conditions=["recherche", "fichiers"],
        action_template="grep -r {{STRING}} {{PATH}}"
    )
    assert skill.id.startswith("sk_"), "Skill ID should start with sk_"
    print(f"  Skill créé: {skill.id}")

    # Test KnowledgeTriple
    triple = KnowledgeTriple(
        id="",
        subject="Python",
        predicate="is_a",
        object="programming language"
    )
    assert triple.id.startswith("kg_"), "Triple ID should start with kg_"
    print(f"  Triple créé: {triple.id}")

    # Test MemoryScore
    score = MemoryScore(
        similarity=0.8,
        importance=0.7,
        recency=0.9,
        access_frequency=0.5
    )
    assert 0 <= score.combined_score <= 1, "Score should be between 0 and 1"
    print(f"  Score combiné: {score.combined_score:.3f}")

    # Test recency calculation
    recency = calculate_recency_score("2026-01-15T00:00:00")
    assert 0 <= recency <= 1, "Recency should be between 0 and 1"
    print(f"  Récence: {recency:.3f}")

    print("  OK!")


def test_episodic_memory():
    """Test de la mémoire épisodique."""
    print("Test: episodic_memory...")

    with tempfile.TemporaryDirectory() as tmpdir:
        from episodic_memory import EpisodicMemory

        memory = EpisodicMemory(storage_path=Path(tmpdir))

        # Enregistrer un épisode
        ep_id = memory.record_interaction(
            context="Test de la mémoire épisodique",
            action="Créer un épisode de test",
            outcome="Épisode créé avec succès",
            thought_process="Test automatique",
            importance=0.8,
            emotional_valence=0.5
        )
        print(f"  Épisode créé: {ep_id}")

        # Rappeler l'épisode
        results = memory.recall("test mémoire", n_results=1)
        assert len(results) >= 1, "Should find at least one episode"
        episode, score = results[0]
        print(f"  Rappelé: {episode.id} (score: {score.combined_score:.3f})")

        # Stats
        stats = memory.get_stats()
        print(f"  Total épisodes: {stats['total_episodes']}")

        print("  OK!")


def test_procedural_memory():
    """Test de la mémoire procédurale."""
    print("Test: procedural_memory...")

    with tempfile.TemporaryDirectory() as tmpdir:
        from procedural_memory import ProceduralMemory

        memory = ProceduralMemory(storage_path=Path(tmpdir))

        # Créer un skill
        skill_id = memory.create_skill(
            name="test_skill",
            description="Skill de test",
            pattern="commande test",
            trigger_conditions=["test", "commande"],
            action_template="echo {{STRING}}"
        )
        print(f"  Skill créé: {skill_id}")

        # Trouver un skill
        results = memory.find_applicable_skills("test commande", n_results=1)
        assert len(results) >= 1, "Should find at least one skill"
        skill, score = results[0]
        print(f"  Trouvé: {skill.name} (score: {score.combined_score:.3f})")

        # Enregistrer une utilisation
        memory.record_usage(skill_id, success=True)
        updated_skill = memory.get_skill(skill_id)
        print(f"  Success rate: {updated_skill.success_rate:.1%}")

        print("  OK!")


def test_knowledge_graph():
    """Test du graphe de connaissances."""
    print("Test: knowledge_graph...")

    with tempfile.TemporaryDirectory() as tmpdir:
        from knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(storage_path=Path(tmpdir))

        # Ajouter des triplets
        id1 = kg.add_triple("Python", "is_a", "programming language")
        id2 = kg.add_triple("Python", "uses", "indentation")
        id3 = kg.add_triple("Aura", "written_in", "Python")
        print(f"  Triplets créés: {id1}, {id2}, {id3}")

        # Recherche sémantique
        results = kg.query_semantic("Python programming", n_results=2)
        print(f"  Trouvé {len(results)} triplet(s)")

        # Relations d'une entité
        relations = kg.get_relations("Python")
        print(f"  Relations de Python: {len(relations)}")

        # Trouver un chemin
        path = kg.get_path("Aura", "programming language")
        if path:
            print(f"  Chemin trouvé: {len(path)} étapes")
        else:
            print("  Pas de chemin direct (normal)")

        print("  OK!")


def test_consolidator():
    """Test du consolidateur."""
    print("Test: memory_consolidator...")

    with tempfile.TemporaryDirectory() as tmpdir:
        from episodic_memory import EpisodicMemory
        from procedural_memory import ProceduralMemory
        from knowledge_graph import KnowledgeGraph
        from memory_consolidator import MemoryConsolidator

        episodic = EpisodicMemory(storage_path=Path(tmpdir) / "ep")
        procedural = ProceduralMemory(storage_path=Path(tmpdir) / "proc")
        knowledge = KnowledgeGraph(storage_path=Path(tmpdir) / "kg")

        consolidator = MemoryConsolidator(episodic, procedural, knowledge)

        # Ajouter quelques épisodes
        for i in range(5):
            episodic.record_interaction(
                context=f"Contexte test {i}",
                action=f"Action similaire {i}",
                outcome="Succès",
                importance=0.7,
                emotional_valence=0.5
            )

        # Analyser les patterns
        analysis = consolidator.analyze_patterns(limit=10)
        print(f"  Épisodes analysés: {analysis['total_episodes']}")
        print(f"  Patterns trouvés: {len(analysis['pattern_groups'])}")

        # Consolidation (dry run)
        result = consolidator.consolidate(min_episodes=3, dry_run=True)
        print(f"  Dry-run: {result.episodes_processed} épisodes traités")

        print("  OK!")


def test_memory_api():
    """Test de l'API unifiée."""
    print("Test: memory_api...")

    with tempfile.TemporaryDirectory() as tmpdir:
        from memory_api import MemoryAPI

        api = MemoryAPI(base_path=Path(tmpdir))

        # Test fichiers mémoire
        result = api.create_file("test.txt", "Contenu de test")
        print(f"  Fichier créé: {result['filename']}")

        result = api.read_file("test.txt")
        assert result["content"] == "Contenu de test"
        print(f"  Fichier lu: {len(result['content'])} chars")

        # Test remember/search
        api.remember("Python est un langage de programmation", memory_type="fact")
        print("  Fait mémorisé")

        # Test épisode
        result = api.record_episode(
            context="Test API",
            action="Tester l'API",
            outcome="Succès"
        )
        print(f"  Épisode: {result['episode_id']}")

        # Test knowledge
        result = api.add_knowledge("Test", "is_a", "API")
        print(f"  Triple: {result['triple_id']}")

        # Stats
        stats = api.get_stats()
        print(f"  Version: {stats['version']}")

        print("  OK!")


def main():
    """Lance tous les tests."""
    print("=" * 50)
    print("Tests du système de mémoire Aura v3.1")
    print("=" * 50)
    print()

    tests = [
        test_memory_types,
        test_episodic_memory,
        test_procedural_memory,
        test_knowledge_graph,
        test_consolidator,
        test_memory_api
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ÉCHEC: {e}")
            failed += 1
        print()

    print("=" * 50)
    print(f"Résultats: {passed} passés, {failed} échoués")
    print("=" * 50)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
