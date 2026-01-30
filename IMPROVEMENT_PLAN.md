# AURA-OS Improvement Plan v3.0
> Date: 2026-01-15 | Status: En cours d'implémentation

---

## RÉSUMÉ EXÉCUTIF

Ce plan détaille les améliorations à apporter au système AURA-OS basées sur l'audit des meilleures pratiques et tendances 2026.

### Objectifs
1. **Mémoire persistante** via RAG (Retrieval-Augmented Generation)
2. **Automatisation événementielle** via inotify/systemd
3. **Validation automatique** avant confirmation de tâches
4. **Context engineering** pour optimiser les interactions LLM

---

## 1. RAG / KNOWLEDGE LAYER

### Objectif
Permettre à Aura de se souvenir des conversations passées, d'indexer les fichiers locaux, et de fournir des réponses contextuellement enrichies.

### Technologies choisies
- **ChromaDB** : Base vectorielle locale, légère, persistante
- **Sentence-Transformers** : Embeddings locaux (all-MiniLM-L6-v2)
- **LangChain** (optionnel) : Orchestration RAG

### Architecture
```
~/.aura/memory/
├── chroma_db/           # Base vectorielle ChromaDB
├── documents/           # Documents indexés
├── conversations/       # Historique des conversations
└── cache/              # Cache sémantique
```

### Paramètres optimaux (best practices 2026)
- **Chunk size** : 1000 caractères
- **Chunk overlap** : 200 caractères
- **Embedding model** : all-MiniLM-L6-v2 (rapide, local)
- **Top-K retrieval** : 5 documents

### Agent à créer
- `memory_manager.py` : Gestion de la mémoire vectorielle
  - `index` : Indexer un fichier/dossier
  - `search` : Rechercher dans la mémoire
  - `remember` : Sauvegarder une conversation
  - `recall` : Rappeler le contexte pertinent
  - `forget` : Supprimer des entrées
  - `stats` : Statistiques de la base

### Dépendances à installer
```bash
pip install chromadb sentence-transformers langchain
```

---

## 2. EVENT-DRIVEN TRIGGERS

### Objectif
Permettre à Aura de réagir automatiquement aux événements système sans polling.

### Technologies choisies
- **inotify-tools** : Surveillance filesystem Linux
- **systemd path units** : Triggers natifs systemd
- **Python watchdog** : Alternative cross-platform

### Événements à surveiller

| Événement | Chemin | Action |
|-----------|--------|--------|
| Nouveau fichier | ~/Downloads | file_organizer.py |
| Modification config | ~/.aura/ | backup + reload |
| Haute CPU (>80%) | /proc | alert + process_manager |
| Nouveau screenshot | ~/Pictures/Screenshots | screenshot_ocr.py |
| Fichier .md créé | ~/Documents | index dans RAG |

### Architecture
```
~/.aura/triggers/
├── file_watcher.py      # Service principal inotify
├── rules.json           # Règles événement -> action
└── systemd/
    ├── aura-watcher.service
    └── aura-watcher.path
```

### Agent à créer
- `event_watcher.py` : Surveillance événementielle
  - `start` : Démarrer la surveillance
  - `stop` : Arrêter
  - `status` : État actuel
  - `add-rule` : Ajouter une règle
  - `list-rules` : Lister les règles

### Service systemd
```ini
[Unit]
Description=Aura Event Watcher
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/tinkerbell/.aura/agents/event_watcher.py start
Restart=on-failure
User=tinkerbell

[Install]
WantedBy=default.target
```

---

## 3. HOOKS D'AUTOMATISATION

### Objectif
Valider automatiquement les tâches avant de les marquer comme terminées.

### Règles de validation

| Type de tâche | Validation requise |
|---------------|-------------------|
| Code Python | `python -m py_compile` + tests si présents |
| Code JS/TS | `eslint` + tests si présents |
| Config YAML | `yamllint` |
| Commit Git | Pre-commit hooks |
| Fichier créé | Vérifier existence et non-vide |

### Architecture
```
~/.aura/hooks/
├── pre_completion.py    # Validations avant "done"
├── validators/
│   ├── python_validator.py
│   ├── js_validator.py
│   ├── yaml_validator.py
│   └── file_validator.py
└── config.json          # Configuration des hooks
```

### Agent à créer
- `completion_validator.py` : Validation pré-complétion
  - `validate` : Valider une tâche
  - `configure` : Configurer les règles
  - `skip` : Ignorer validation (avec raison)

### Intégration Claude Code
Ajouter dans les règles AURA_SYSTEM.md :
```
AVANT de marquer une tâche comme terminée :
1. Identifier le type de tâche (code, config, fichier)
2. Exécuter completion_validator.py validate
3. Si échec : corriger et réessayer
4. Si succès : marquer comme terminé
```

---

## 4. CONTEXT PACKING / BRAIN DUMP

### Objectif
Optimiser le contexte fourni au LLM pour chaque tâche.

### Techniques à implémenter

1. **Brain Dump Template**
   - Goals : Objectifs de la tâche
   - Constraints : Contraintes à respecter
   - Examples : Exemples de bons résultats
   - Anti-patterns : Ce qu'il faut éviter

2. **Scratchpad**
   - Notes intermédiaires persistantes
   - Résultats partiels
   - Décisions prises

3. **Context Compression**
   - Résumés au lieu de fichiers complets
   - Signatures de fonctions au lieu de code entier
   - Métadonnées pertinentes seulement

### Architecture
```
~/.aura/context/
├── templates/
│   ├── coding_task.md
│   ├── research_task.md
│   ├── system_task.md
│   └── creative_task.md
├── scratchpad/
│   └── current_session.md
└── summaries/
    └── project_contexts/
```

### Agent à créer
- `context_engineer.py` : Gestion du contexte
  - `prepare` : Préparer le contexte pour une tâche
  - `compress` : Compresser un fichier/dossier
  - `scratchpad` : Gérer le scratchpad
  - `summarize` : Résumer un projet

### Template Brain Dump
```markdown
# Context pour: {task_name}

## Objectifs
- {goal_1}
- {goal_2}

## Contraintes
- {constraint_1}
- {constraint_2}

## Exemples de bon résultat
{example}

## À éviter
- {anti_pattern_1}
- {anti_pattern_2}

## Contexte projet
{compressed_context}
```

---

## 5. PLANNING D'IMPLÉMENTATION

### Phase 1 : RAG/Memory (Priorité haute)
1. Installer dépendances (chromadb, sentence-transformers)
2. Créer `memory_manager.py`
3. Indexer ~/.aura/ et ~/Documents
4. Tester recherche et recall

### Phase 2 : Event Triggers (Priorité haute)
1. Installer inotify-tools
2. Créer `event_watcher.py`
3. Configurer règles pour Downloads
4. Créer service systemd

### Phase 3 : Validation Hooks (Priorité moyenne)
1. Créer `completion_validator.py`
2. Implémenter validateurs par type
3. Intégrer dans workflow Aura

### Phase 4 : Context Engineering (Priorité moyenne)
1. Créer templates de contexte
2. Implémenter `context_engineer.py`
3. Créer système de scratchpad

### Phase 5 : Documentation & Tests
1. Mettre à jour AURA_SYSTEM.md
2. Mettre à jour agents_manifest.json
3. Tester l'ensemble du système

---

## 6. MÉTRIQUES DE SUCCÈS

| Métrique | Objectif |
|----------|----------|
| Temps de réponse contextuelle | < 2s |
| Précision recall mémoire | > 85% |
| Taux de validation auto | > 90% |
| Événements traités/jour | Illimité |
| Tokens économisés (context) | > 30% |

---

## SOURCES & RÉFÉRENCES

- [RAG with LangChain & ChromaDB](https://medium.com/@saubhagya.vishwakarma113393/retrieval-augmented-generation-rag-with-langchain-chromadb-and-faiss-a-complete-guide-63ad903a237a)
- [Linux inotify Guide](https://www.linuxjournal.com/content/linux-filesystem-events-inotify)
- [Pre-commit Hooks Guide 2025](https://gatlenculp.medium.com/effortless-code-quality-the-ultimate-pre-commit-hooks-guide-for-2025-57ca501d9835)
- [Context Engineering - Addy Osmani](https://addyo.substack.com/p/context-engineering-bringing-engineering)
- [IBM Prompt Engineering Guide 2026](https://www.ibm.com/think/prompt-engineering)

---

*Plan créé le 2026-01-15 par Aura-OS*
