#!/home/tinkerbell/.aura/venv/bin/python3
"""
Aura Intent Router v1.0
Classification des intentions et routage vers les agents appropriés.

Basé sur:
- Embedding-based semantic matching
- Keyword fallback
- Confidence thresholds
- Multi-agent routing for complex requests
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

# Configuration
AGENTS_DIR = Path(__file__).parent
CONFIG_DIR = Path.home() / ".aura"
ROUTING_CONFIG = CONFIG_DIR / "routing_config.json"

# Seuils
CONFIDENCE_THRESHOLD = 0.6  # Minimum pour router
HIGH_CONFIDENCE = 0.85      # Routage direct sans vérification
MULTI_AGENT_THRESHOLD = 0.5 # Pour détecter plusieurs agents pertinents


@dataclass
class AgentCapability:
    """Capacité d'un agent."""
    name: str
    description: str
    keywords: List[str]
    patterns: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None
    priority: int = 5  # 1-10, 10 = priorité max
    requires_background: bool = False
    typical_duration: str = "quick"  # quick, medium, long


@dataclass
class RoutingDecision:
    """Décision de routage."""
    primary_agent: str
    confidence: float
    secondary_agents: List[Tuple[str, float]] = field(default_factory=list)
    reasoning: str = ""
    run_parallel: bool = False
    run_background: bool = False
    requires_confirmation: bool = False


# Table de routage statique (fallback si pas d'embeddings)
ROUTING_TABLE: Dict[str, AgentCapability] = {
    # === SYSTÈME ===
    "sys_health": AgentCapability(
        name="sys_health",
        description="Monitoring santé système: CPU, RAM, température, disques",
        keywords=["cpu", "ram", "mémoire", "température", "temp", "disque", "espace",
                  "santé", "health", "système", "system", "performance", "charge",
                  "swap", "processeur", "gpu"],
        patterns=[r"comment va (le système|mon pc)", r"état (du|de mon) (système|pc|ordinateur)"],
        priority=7,
        typical_duration="quick"
    ),

    "process_manager": AgentCapability(
        name="process_manager",
        description="Gestion des processus: lister, tuer, top consommateurs",
        keywords=["processus", "process", "pid", "kill", "tuer", "arrêter", "top",
                  "consomme", "gourmand", "lent", "freeze", "bloqué", "hung"],
        patterns=[r"tue(r)? (le )?process", r"quel process", r"qui consomme"],
        priority=8,
        typical_duration="quick"
    ),

    "plasma_controller": AgentCapability(
        name="plasma_controller",
        description="Contrôle KDE Plasma: fenêtres, bureaux virtuels, widgets",
        keywords=["fenêtre", "window", "bureau", "desktop", "kde", "plasma",
                  "widget", "panel", "écran", "screen", "workspace"],
        patterns=[r"(ouvre|ferme|déplace) (la )?fenêtre", r"bureau virtuel"],
        priority=6,
        typical_duration="quick"
    ),

    "system_cleaner": AgentCapability(
        name="system_cleaner",
        description="Nettoyage système: cache, logs, fichiers temporaires",
        keywords=["nettoyer", "clean", "cache", "temp", "temporaire", "logs",
                  "obsolète", "vieux", "ancien", "libérer", "espace"],
        patterns=[r"nettoie(r)? (le )?(système|cache|logs)", r"libère(r)? de l'espace"],
        priority=6,
        requires_background=True,
        typical_duration="medium"
    ),

    "claude_cleaner": AgentCapability(
        name="claude_cleaner",
        description="Nettoie les processus Claude orphelins",
        keywords=["claude", "orphelin", "zombie", "claude code", "anthropic"],
        patterns=[r"process(us)? claude", r"claude (orphelin|zombie)"],
        priority=5,
        typical_duration="quick"
    ),

    "app_installer": AgentCapability(
        name="app_installer",
        description="Installation d'applications: apt, flatpak, snap",
        keywords=["installer", "install", "désinstaller", "uninstall", "apt",
                  "flatpak", "snap", "package", "paquet", "application", "app",
                  "logiciel", "software", "mise à jour", "update", "upgrade"],
        patterns=[r"install(e|er)? ", r"met(s|tre)? à jour"],
        priority=7,
        requires_background=True,
        typical_duration="long"
    ),

    # === SÉCURITÉ ===
    "security_auditor": AgentCapability(
        name="security_auditor",
        description="Audit sécurité: ports, SSH, firewall, vulnérabilités",
        keywords=["sécurité", "security", "audit", "port", "ssh", "firewall",
                  "ufw", "vulnérabilité", "faille", "intrusion", "hack"],
        patterns=[r"audit(e|er)? (la )?sécurité", r"ports ouverts", r"config ssh"],
        priority=8,
        requires_background=True,
        typical_duration="medium"
    ),

    "network_monitor": AgentCapability(
        name="network_monitor",
        description="Surveillance réseau: connexions, bande passante, interfaces",
        keywords=["réseau", "network", "connexion", "connection", "internet",
                  "wifi", "ethernet", "ip", "bandwidth", "bande passante",
                  "ping", "latence", "dns"],
        patterns=[r"état (du )?réseau", r"connexions? (actives?|ouvertes?)"],
        priority=7,
        typical_duration="quick"
    ),

    # === VOIX ===
    "voice_speak": AgentCapability(
        name="voice_speak",
        description="Synthèse vocale avec Edge-TTS",
        keywords=["parle", "dis", "voix", "voice", "speak", "tts", "audio"],
        patterns=[r"dis (moi|lui|nous)", r"parle"],
        priority=9,
        typical_duration="quick"
    ),

    # === INFO ===
    "tech_watcher": AgentCapability(
        name="tech_watcher",
        description="Veille technologique: HN, Reddit, Lobsters",
        keywords=["news", "actualité", "tech", "hacker news", "reddit", "lobsters",
                  "veille", "trending", "tendance"],
        patterns=[r"(quoi de )?neuf (en tech|dans la tech)", r"actualités? tech"],
        priority=5,
        requires_background=True,
        typical_duration="medium"
    ),

    # === FICHIERS ===
    "file_organizer": AgentCapability(
        name="file_organizer",
        description="Organisation automatique des fichiers",
        keywords=["organiser", "ranger", "trier", "fichier", "file", "dossier",
                  "folder", "téléchargement", "download", "documents"],
        patterns=[r"(range|organise|trie)(r)? (les|mes) (fichiers|téléchargements)"],
        priority=6,
        requires_background=True,
        typical_duration="medium"
    ),

    "screenshot_ocr": AgentCapability(
        name="screenshot_ocr",
        description="OCR sur captures d'écran",
        keywords=["ocr", "screenshot", "capture", "écran", "texte", "image",
                  "extraire", "lire"],
        patterns=[r"(lis|extrait|ocr) (le texte|l'image|la capture)"],
        priority=6,
        typical_duration="quick"
    ),

    # === MÉMOIRE ===
    "memory_manager": AgentCapability(
        name="memory_manager",
        description="Système de mémoire RAG: indexation, recherche, rappel",
        keywords=["mémoire", "memory", "rappel", "souvenir", "remember",
                  "index", "recherche", "rag", "contexte", "historique"],
        patterns=[r"(rappelle|souviens|mémorise)", r"dans (ta|la) mémoire"],
        priority=8,
        typical_duration="quick"
    ),

    # === META ===
    "agent_factory": AgentCapability(
        name="agent_factory",
        description="Création et gestion d'agents Aura",
        keywords=["créer agent", "nouvel agent", "agent factory", "générer agent"],
        patterns=[r"(crée|génère|nouveau) (un )?agent"],
        priority=7,
        typical_duration="medium"
    ),

    "task_runner": AgentCapability(
        name="task_runner",
        description="Exécution de tâches en arrière-plan",
        keywords=["background", "arrière-plan", "tâche", "task", "parallèle"],
        patterns=[r"en (arrière-plan|background)", r"lance (en fond|parallèle)"],
        priority=8,
        typical_duration="quick"
    ),

    "logger_master": AgentCapability(
        name="logger_master",
        description="Logging centralisé Aura",
        keywords=["log", "journal", "trace", "historique", "enregistrer"],
        patterns=[r"(log|enregistre|trace)"],
        priority=4,
        typical_duration="quick"
    ),
}


class IntentRouter:
    """Routeur d'intentions basé sur embeddings et keywords."""

    def __init__(self, use_embeddings: bool = True):
        self.use_embeddings = use_embeddings
        self.routing_table = ROUTING_TABLE.copy()
        self.embedder = None
        self._load_custom_config()

        if use_embeddings:
            self._init_embedder()

    def _load_custom_config(self):
        """Charge une config de routage personnalisée."""
        if ROUTING_CONFIG.exists():
            try:
                custom = json.loads(ROUTING_CONFIG.read_text())
                for name, data in custom.get("agents", {}).items():
                    if name in self.routing_table:
                        # Étendre les keywords
                        self.routing_table[name].keywords.extend(
                            data.get("extra_keywords", [])
                        )
                        self.routing_table[name].patterns.extend(
                            data.get("extra_patterns", [])
                        )
            except Exception:
                pass

    def _init_embedder(self):
        """Initialise le modèle d'embeddings."""
        try:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer('all-MiniLM-L6-v2')

            # Pré-calculer les embeddings des descriptions
            for cap in self.routing_table.values():
                text = f"{cap.description} {' '.join(cap.keywords)}"
                cap.embedding = self.embedder.encode(text).tolist()
        except ImportError:
            self.use_embeddings = False
            self.embedder = None

    def _keyword_match(self, query: str) -> List[Tuple[str, float]]:
        """Match basé sur les keywords."""
        query_lower = query.lower()
        scores = []

        for name, cap in self.routing_table.items():
            score = 0.0
            matches = 0

            # Keywords
            for kw in cap.keywords:
                if kw.lower() in query_lower:
                    matches += 1
                    score += 0.15

            # Patterns regex
            for pattern in cap.patterns:
                if re.search(pattern, query_lower):
                    score += 0.3
                    matches += 1

            # Bonus si plusieurs matches
            if matches > 2:
                score *= 1.2

            if score > 0:
                scores.append((name, min(score, 1.0)))

        return sorted(scores, key=lambda x: x[1], reverse=True)

    def _embedding_match(self, query: str) -> List[Tuple[str, float]]:
        """Match basé sur les embeddings."""
        if not self.embedder:
            return []

        query_emb = self.embedder.encode(query)
        scores = []

        for name, cap in self.routing_table.items():
            if cap.embedding:
                # Cosine similarity
                import numpy as np
                cap_emb = np.array(cap.embedding)
                similarity = np.dot(query_emb, cap_emb) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(cap_emb)
                )
                scores.append((name, float(similarity)))

        return sorted(scores, key=lambda x: x[1], reverse=True)

    def _combine_scores(
        self,
        keyword_scores: List[Tuple[str, float]],
        embedding_scores: List[Tuple[str, float]]
    ) -> List[Tuple[str, float]]:
        """Combine les scores keywords et embeddings."""
        combined = {}

        # Keywords (poids 0.4)
        for name, score in keyword_scores:
            combined[name] = combined.get(name, 0) + score * 0.4

        # Embeddings (poids 0.6)
        for name, score in embedding_scores:
            combined[name] = combined.get(name, 0) + score * 0.6

        # Appliquer les priorités
        for name in combined:
            priority = self.routing_table[name].priority / 10.0
            combined[name] *= (0.8 + priority * 0.2)

        return sorted(combined.items(), key=lambda x: x[1], reverse=True)

    def route(self, query: str) -> RoutingDecision:
        """
        Route une requête vers le(s) agent(s) approprié(s).

        Args:
            query: La requête utilisateur

        Returns:
            RoutingDecision avec l'agent principal et les agents secondaires
        """
        # Scores keywords
        kw_scores = self._keyword_match(query)

        # Scores embeddings
        emb_scores = self._embedding_match(query) if self.use_embeddings else []

        # Combiner
        if emb_scores:
            combined = self._combine_scores(kw_scores, emb_scores)
        else:
            combined = kw_scores

        if not combined:
            return RoutingDecision(
                primary_agent="",
                confidence=0.0,
                reasoning="Aucun agent trouvé pour cette requête"
            )

        # Agent principal
        primary_name, primary_score = combined[0]
        primary_cap = self.routing_table[primary_name]

        # Agents secondaires (si score > seuil)
        secondary = [
            (name, score) for name, score in combined[1:5]
            if score >= MULTI_AGENT_THRESHOLD
        ]

        # Déterminer si exécution en background
        run_bg = primary_cap.requires_background or primary_cap.typical_duration != "quick"

        # Déterminer si plusieurs agents en parallèle
        run_parallel = len(secondary) > 0 and all(
            self.routing_table[name].typical_duration == "quick"
            for name, _ in secondary[:2]
        )

        # Confirmation nécessaire si confiance moyenne
        requires_confirm = CONFIDENCE_THRESHOLD <= primary_score < HIGH_CONFIDENCE

        return RoutingDecision(
            primary_agent=primary_name,
            confidence=primary_score,
            secondary_agents=secondary,
            reasoning=f"Match principal: {primary_name} ({primary_score:.2f})",
            run_parallel=run_parallel,
            run_background=run_bg,
            requires_confirmation=requires_confirm
        )

    def get_agent_info(self, agent_name: str) -> Optional[AgentCapability]:
        """Récupère les infos d'un agent."""
        return self.routing_table.get(agent_name)

    def list_agents(self) -> List[Dict[str, Any]]:
        """Liste tous les agents disponibles."""
        return [
            {
                "name": cap.name,
                "description": cap.description,
                "keywords": cap.keywords[:5],
                "priority": cap.priority,
                "background": cap.requires_background
            }
            for cap in sorted(
                self.routing_table.values(),
                key=lambda c: c.priority,
                reverse=True
            )
        ]

    def add_agent(self, agent: AgentCapability):
        """Ajoute un agent au routeur."""
        self.routing_table[agent.name] = agent

        # Recalculer embedding si disponible
        if self.embedder and agent.embedding is None:
            text = f"{agent.description} {' '.join(agent.keywords)}"
            agent.embedding = self.embedder.encode(text).tolist()


def route_query(query: str, use_embeddings: bool = True) -> Dict[str, Any]:
    """Fonction helper pour routage rapide."""
    router = IntentRouter(use_embeddings=use_embeddings)
    decision = router.route(query)

    return {
        "primary_agent": decision.primary_agent,
        "confidence": decision.confidence,
        "secondary_agents": [
            {"agent": name, "score": score}
            for name, score in decision.secondary_agents
        ],
        "run_background": decision.run_background,
        "run_parallel": decision.run_parallel,
        "requires_confirmation": decision.requires_confirmation,
        "reasoning": decision.reasoning
    }


def main():
    parser = argparse.ArgumentParser(
        description="Aura Intent Router - Classification et routage des intentions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s route "Montre-moi les processus qui consomment le plus"
  %(prog)s route "Fais un audit de sécurité complet" --no-embeddings
  %(prog)s list
  %(prog)s info sys_health
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    # route
    route_p = subparsers.add_parser("route", help="Router une requête")
    route_p.add_argument("query", help="Requête à router")
    route_p.add_argument("--no-embeddings", action="store_true",
                        help="Désactiver le matching par embeddings")
    route_p.add_argument("--json", action="store_true", help="Sortie JSON")

    # list
    subparsers.add_parser("list", help="Lister tous les agents")

    # info
    info_p = subparsers.add_parser("info", help="Infos sur un agent")
    info_p.add_argument("agent", help="Nom de l'agent")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    router = IntentRouter(use_embeddings=not getattr(args, 'no_embeddings', False))

    if args.command == "route":
        decision = router.route(args.query)

        if args.json:
            result = route_query(args.query, not args.no_embeddings)
            print(json.dumps(result, indent=2))
        else:
            print(f"Agent principal: {decision.primary_agent}")
            print(f"Confiance: {decision.confidence:.2%}")

            if decision.secondary_agents:
                print(f"\nAgents secondaires:")
                for name, score in decision.secondary_agents:
                    print(f"  - {name}: {score:.2%}")

            print(f"\nOptions:")
            print(f"  Background: {decision.run_background}")
            print(f"  Parallèle: {decision.run_parallel}")
            print(f"  Confirmation: {decision.requires_confirmation}")
            print(f"\nRaisonnement: {decision.reasoning}")

    elif args.command == "list":
        agents = router.list_agents()
        print(f"{'Agent':<20} {'Priorité':<10} {'Background':<12} Description")
        print("-" * 80)
        for a in agents:
            bg = "Oui" if a["background"] else "Non"
            print(f"{a['name']:<20} {a['priority']:<10} {bg:<12} {a['description'][:40]}")

    elif args.command == "info":
        cap = router.get_agent_info(args.agent)
        if cap:
            print(f"Agent: {cap.name}")
            print(f"Description: {cap.description}")
            print(f"Keywords: {', '.join(cap.keywords)}")
            print(f"Patterns: {cap.patterns}")
            print(f"Priorité: {cap.priority}")
            print(f"Background: {cap.requires_background}")
            print(f"Durée typique: {cap.typical_duration}")
        else:
            print(f"Agent non trouvé: {args.agent}")


if __name__ == "__main__":
    main()
