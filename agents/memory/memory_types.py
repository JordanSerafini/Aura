#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Memory Types - Définitions des types de mémoire v3.1
Architecture multi-niveaux inspirée de MIRIX et des recherches cognitives.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from typing import Any
import json
import hashlib


class MemoryType(Enum):
    """Types de mémoire supportés par Aura."""
    CORE = auto()        # Identité, préférences fondamentales
    EPISODIC = auto()    # Interactions passées, contexte complet
    SEMANTIC = auto()    # Faits, concepts, connaissances
    PROCEDURAL = auto()  # Skills, patterns appris
    WORKING = auto()     # Contexte conversation actuelle
    KNOWLEDGE = auto()   # Graphe de connaissances (triplets)


class MemoryPriority(Enum):
    """Priorité des souvenirs pour le scoring."""
    CRITICAL = 5    # Ne jamais oublier
    HIGH = 4        # Très important
    NORMAL = 3      # Standard
    LOW = 2         # Peut être oublié
    EPHEMERAL = 1   # Temporaire


class MemoryStatus(Enum):
    """État d'un souvenir."""
    ACTIVE = auto()      # Actif et utilisable
    ARCHIVED = auto()    # Archivé mais récupérable
    CONSOLIDATED = auto() # Fusionné avec d'autres souvenirs
    DEPRECATED = auto()   # Marqué pour suppression


@dataclass
class MemoryMetadata:
    """Métadonnées communes à tous les types de mémoire."""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    last_accessed: str | None = None
    source: str = "user"  # user, system, agent, consolidation
    tags: list[str] = field(default_factory=list)
    priority: int = MemoryPriority.NORMAL.value
    status: str = MemoryStatus.ACTIVE.name

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'MemoryMetadata':
        return cls(**data)


@dataclass
class Episode:
    """
    Représente un épisode de mémoire épisodique.
    Capture le contexte complet d'une interaction.
    """
    id: str
    timestamp: str
    context: str           # Situation/contexte de l'épisode
    action: str            # Action effectuée
    outcome: str           # Résultat (success/failure + détails)
    thought_process: str   # Raisonnement qui a mené à l'action
    entities: list[str]    # Entités impliquées
    emotional_valence: float = 0.0  # -1 (négatif) à +1 (positif)
    importance: float = 0.5  # 0 à 1
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()

    def _generate_id(self) -> str:
        data = f"{self.timestamp}:{self.context[:50]}:{self.action[:50]}"
        return f"ep_{hashlib.sha256(data.encode()).hexdigest()[:12]}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d['metadata'] = self.metadata.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Episode':
        if 'metadata' in data and isinstance(data['metadata'], dict):
            data['metadata'] = MemoryMetadata.from_dict(data['metadata'])
        return cls(**data)


@dataclass
class Skill:
    """
    Représente un skill/pattern appris (mémoire procédurale).
    Extrait de la consolidation des épisodes réussis.
    """
    id: str
    name: str
    description: str
    pattern: str           # Pattern général appris
    trigger_conditions: list[str]  # Quand appliquer ce skill
    action_template: str   # Template d'action à exécuter
    success_rate: float = 0.0
    usage_count: int = 0
    source_episodes: list[str] = field(default_factory=list)  # IDs des épisodes sources
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()

    def _generate_id(self) -> str:
        data = f"{self.name}:{self.pattern[:50]}"
        return f"sk_{hashlib.sha256(data.encode()).hexdigest()[:12]}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d['metadata'] = self.metadata.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'Skill':
        if 'metadata' in data and isinstance(data['metadata'], dict):
            data['metadata'] = MemoryMetadata.from_dict(data['metadata'])
        return cls(**data)


@dataclass
class KnowledgeTriple:
    """
    Triplet de connaissance pour le graphe (style AriGraph).
    Représente une relation: sujet -> relation -> objet
    """
    id: str
    subject: str
    predicate: str  # Type de relation
    object: str
    confidence: float = 1.0  # Confiance dans ce triplet
    source_episode: str | None = None  # Lien vers l'épisode source
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)

    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()

    def _generate_id(self) -> str:
        data = f"{self.subject}:{self.predicate}:{self.object}"
        return f"kg_{hashlib.sha256(data.encode()).hexdigest()[:12]}"

    def to_text(self) -> str:
        """Représentation textuelle pour l'embedding."""
        return f"{self.subject} {self.predicate} {self.object}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d['metadata'] = self.metadata.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'KnowledgeTriple':
        if 'metadata' in data and isinstance(data['metadata'], dict):
            data['metadata'] = MemoryMetadata.from_dict(data['metadata'])
        return cls(**data)


@dataclass
class MemoryScore:
    """
    Score de pertinence d'un souvenir.
    Combine similarité, importance et récence.
    """
    similarity: float      # Similarité sémantique (0-1)
    importance: float      # Importance du souvenir (0-1)
    recency: float         # Fraîcheur (0-1, décroît avec le temps)
    access_frequency: float = 0.0  # Fréquence d'accès normalisée

    @property
    def combined_score(self) -> float:
        """
        Score combiné avec pondération.
        Formule: similarity × 0.4 + importance × 0.3 + recency × 0.2 + frequency × 0.1
        """
        return (
            self.similarity * 0.4 +
            self.importance * 0.3 +
            self.recency * 0.2 +
            self.access_frequency * 0.1
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'similarity': self.similarity,
            'importance': self.importance,
            'recency': self.recency,
            'access_frequency': self.access_frequency,
            'combined': self.combined_score
        }


@dataclass
class ConsolidationResult:
    """Résultat d'une opération de consolidation."""
    episodes_processed: int
    skills_created: int
    skills_updated: int
    triples_extracted: int
    episodes_archived: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    details: dict[str, Any] = field(default_factory=dict)


# Configuration par défaut du système de mémoire
MEMORY_CONFIG = {
    "chunk_size": 512,  # Optimal selon recherches 2025
    "chunk_overlap": 100,
    "embedding_model": "all-MiniLM-L6-v2",  # 384 dimensions, rapide
    "embedding_dimensions": 384,
    "max_latency_ms": 100,
    "recency_decay_days": 30,  # Demi-vie de la récence
    "consolidation_threshold": 10,  # Nb d'épisodes avant consolidation
    "min_skill_occurrences": 3,  # Nb minimum pour créer un skill
    "collections": {
        "episodes": "Mémoire épisodique - interactions complètes",
        "skills": "Mémoire procédurale - patterns appris",
        "knowledge": "Graphe de connaissances - triplets",
        "documents": "Documents indexés",
        "notes": "Notes utilisateur"
    }
}


def calculate_recency_score(timestamp: str, decay_days: int = 30) -> float:
    """
    Calcule le score de récence avec décroissance exponentielle.

    Args:
        timestamp: ISO timestamp du souvenir
        decay_days: Demi-vie en jours

    Returns:
        Score entre 0 et 1 (1 = maintenant, décroît avec le temps)
    """
    from datetime import datetime
    import math

    try:
        memory_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        now = datetime.now(memory_time.tzinfo) if memory_time.tzinfo else datetime.now()
        age_days = (now - memory_time).total_seconds() / 86400

        # Décroissance exponentielle: score = e^(-age/decay)
        return math.exp(-age_days / decay_days)
    except Exception:
        return 0.5  # Valeur par défaut en cas d'erreur


def generate_memory_id(prefix: str, content: str) -> str:
    """Génère un ID unique pour un souvenir."""
    timestamp = datetime.now().isoformat()
    data = f"{timestamp}:{content[:100]}"
    return f"{prefix}_{hashlib.sha256(data.encode()).hexdigest()[:12]}"
