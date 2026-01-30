"""
Aura Memory System v3.1
Architecture multi-niveaux avec mémoire épisodique, procédurale et graphe de connaissances.

Composants:
- memory_types: Définitions des types de mémoire
- episodic_memory: Mémoire épisodique (interactions passées)
- procedural_memory: Mémoire procédurale (skills appris)
- knowledge_graph: Graphe de connaissances (triplets)
- memory_consolidator: Consolidation épisodique → procédurale/sémantique
- memory_api: API CRUD unifiée
"""

from .memory_types import (
    MemoryType,
    MemoryPriority,
    MemoryStatus,
    MemoryMetadata,
    Episode,
    Skill,
    KnowledgeTriple,
    MemoryScore,
    ConsolidationResult,
    MEMORY_CONFIG,
    calculate_recency_score,
    generate_memory_id
)

from .episodic_memory import EpisodicMemory
from .procedural_memory import ProceduralMemory
from .knowledge_graph import KnowledgeGraph
from .memory_consolidator import MemoryConsolidator
from .memory_api import MemoryAPI

__version__ = "3.1.0"
__all__ = [
    # Types
    'MemoryType',
    'MemoryPriority',
    'MemoryStatus',
    'MemoryMetadata',
    'Episode',
    'Skill',
    'KnowledgeTriple',
    'MemoryScore',
    'ConsolidationResult',
    'MEMORY_CONFIG',
    # Functions
    'calculate_recency_score',
    'generate_memory_id',
    # Components
    'EpisodicMemory',
    'ProceduralMemory',
    'KnowledgeGraph',
    'MemoryConsolidator',
    'MemoryAPI'
]
