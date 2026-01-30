#!/usr/bin/env python3
"""
AURA Watchdog - Agent d'auto-surveillance et auto-amélioration
Vérifie si Aura tourne, sinon lance une session d'auto-amélioration autonome.
Inclut aussi l'amélioration automatique du projet EBP_App avec validation des builds.
Exécuté toutes les heures via cron.
"""

import subprocess
import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Chemins
AURA_DIR = Path.home() / ".aura"
LOGS_DIR = Path.home() / "aura_logs" / datetime.now().strftime("%Y-%m-%d")
WATCHDOG_LOG = LOGS_DIR / "watchdog.md"
IMPROVEMENT_SCRIPT = AURA_DIR / "agents" / "aura_self_improve.py"
EBP_APP_DIR = Path.home() / "Desktop" / "Code" / "Projets" / "Ebp_App"

def log(message: str, level: str = "INFO"):
    """Log un message dans le fichier watchdog et dans le reporter"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(WATCHDOG_LOG, "a") as f:
        f.write(f"| {timestamp} | {level} | {message} |\n")
    print(f"[{level}] {message}")

    # Log aussi dans le reporter Aura (rapports Desktop)
    try:
        if level in ["ACTION", "SUCCESS"]:
            subprocess.run([
                "python3", str(AURA_DIR / "agents" / "aura_reporter.py"),
                "action", "--agent", "watchdog", "-m", message[:100], "-r", level
            ], capture_output=True, timeout=5)
        elif level == "ERROR":
            subprocess.run([
                "python3", str(AURA_DIR / "agents" / "aura_reporter.py"),
                "error", "--agent", "watchdog", "-m", message[:100]
            ], capture_output=True, timeout=5)
    except:
        pass  # Ne pas bloquer si le reporter échoue

def check_aura_running() -> bool:
    """Vérifie si un processus Aura/Claude est actif"""
    try:
        # Cherche des processus Claude Code actifs
        result = subprocess.run(
            ["pgrep", "-f", "claude"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            log(f"Processus Claude actifs trouvés: {len(pids)} (PIDs: {', '.join(pids)})")
            return True

        # Vérifie aussi les processus node liés à Claude
        result2 = subprocess.run(
            ["pgrep", "-f", "claude-code"],
            capture_output=True,
            text=True
        )
        if result2.returncode == 0 and result2.stdout.strip():
            log(f"Processus claude-code actifs trouvés")
            return True

        return False
    except Exception as e:
        log(f"Erreur vérification processus: {e}", "ERROR")
        return False

def check_recent_activity() -> bool:
    """Vérifie s'il y a eu une activité récente (dernière heure)"""
    try:
        # Vérifie les logs récents
        today_logs = Path.home() / "aura_logs" / datetime.now().strftime("%Y-%m-%d")
        if today_logs.exists():
            for log_file in today_logs.glob("*.md"):
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                age_minutes = (datetime.now() - mtime).total_seconds() / 60
                if age_minutes < 60:
                    log(f"Activité récente détectée: {log_file.name} (il y a {int(age_minutes)} min)")
                    return True
        return False
    except Exception as e:
        log(f"Erreur vérification activité: {e}", "ERROR")
        return False

def get_improvement_tasks() -> list:
    """Génère une liste de tâches d'auto-amélioration"""
    tasks = [
        "sync_manifest",      # Synchroniser le manifest avec les agents existants
        "check_agents",       # Vérifier la santé des agents
        "analyze_logs",       # Analyser les logs pour détecter des patterns
        "update_stats",       # Mettre à jour les statistiques
        "cleanup_old_logs",   # Nettoyer les vieux logs (>30 jours)
        "optimize_prompts",   # Proposer des optimisations de prompts
    ]
    return tasks

def run_self_improvement():
    """Lance une session d'auto-amélioration autonome"""
    log("🚀 Lancement session auto-amélioration autonome", "ACTION")

    # Créer le script d'amélioration s'il n'existe pas
    if not IMPROVEMENT_SCRIPT.exists():
        log("Script d'amélioration non trouvé, création...", "WARNING")
        create_improvement_script()

    try:
        # Lance Claude Code en mode non-interactif avec une tâche d'amélioration
        improvement_prompt = """
Tu es Aura en mode auto-amélioration autonome (lancé par watchdog).
Effectue les tâches suivantes de manière silencieuse et efficace:

1. **Synchronisation**: Lance `python3 ~/.aura/agents/prompt_evolver.py sync` pour synchroniser la doc
2. **Santé système**: Lance `python3 ~/.aura/agents/sys_health.py` et log les résultats
3. **Nettoyage**: Lance `python3 ~/.aura/agents/claude_cleaner.py clean` pour nettoyer les orphelins
4. **Analyse logs**: Regarde les logs du jour et identifie des patterns d'erreurs récurrentes
5. **Propositions**: Si tu trouves des améliorations possibles, crée un fichier ~/.aura/improvements_suggestions.md

Sois concis, efficace. Pas besoin de vocal (mode automatique).
Log tes actions dans ~/aura_logs/{date}/auto_improve.md
"""

        # Utilise claude avec --print pour mode non-interactif
        result = subprocess.run(
            ["claude", "--print", "-p", improvement_prompt],
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max
            cwd=str(Path.home())
        )

        if result.returncode == 0:
            log("✅ Session auto-amélioration terminée avec succès", "SUCCESS")
            # Sauvegarde le résultat
            output_file = LOGS_DIR / "auto_improve.md"
            with open(output_file, "a") as f:
                f.write(f"\n## Session {datetime.now().strftime('%H:%M')}\n")
                f.write(result.stdout[:2000] if len(result.stdout) > 2000 else result.stdout)
                f.write("\n")
        else:
            log(f"❌ Erreur auto-amélioration: {result.stderr[:200]}", "ERROR")

    except subprocess.TimeoutExpired:
        log("⏱️ Timeout session auto-amélioration (5min)", "WARNING")
    except Exception as e:
        log(f"❌ Exception auto-amélioration: {e}", "ERROR")

def create_improvement_script():
    """Crée le script d'auto-amélioration"""
    script_content = '''#!/usr/bin/env python3
"""Script d'auto-amélioration Aura - appelé par watchdog"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

def run_task(name, cmd):
    print(f"[AUTO] {name}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return result.returncode == 0, result.stdout[:500]
    except:
        return False, "timeout/error"

tasks = [
    ("Sync manifest", "python3 ~/.aura/agents/prompt_evolver.py sync"),
    ("Health check", "python3 ~/.aura/agents/sys_health.py"),
    ("Clean orphans", "python3 ~/.aura/agents/claude_cleaner.py clean"),
]

for name, cmd in tasks:
    success, output = run_task(name, cmd)
    status = "✓" if success else "✗"
    print(f"  {status} {name}")
'''
    IMPROVEMENT_SCRIPT.write_text(script_content)
    IMPROVEMENT_SCRIPT.chmod(0o755)
    log(f"Script créé: {IMPROVEMENT_SCRIPT}")

def check_ebp_app_project() -> dict:
    """Analyse le projet EBP_App et retourne son état"""
    result = {
        "exists": False,
        "has_package_json": False,
        "has_git": False,
        "last_commit": None,
        "uncommitted_changes": False,
        "build_status": None
    }

    if not EBP_APP_DIR.exists():
        log(f"⚠️ Projet EBP_App non trouvé: {EBP_APP_DIR}", "WARNING")
        return result

    result["exists"] = True
    result["has_package_json"] = (EBP_APP_DIR / "package.json").exists()
    result["has_git"] = (EBP_APP_DIR / ".git").exists()

    # Vérifier les changements git
    if result["has_git"]:
        try:
            git_status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=EBP_APP_DIR,
                capture_output=True,
                text=True,
                timeout=10
            )
            result["uncommitted_changes"] = bool(git_status.stdout.strip())

            # Dernier commit
            git_log = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%s (%ar)"],
                cwd=EBP_APP_DIR,
                capture_output=True,
                text=True,
                timeout=10
            )
            result["last_commit"] = git_log.stdout.strip() if git_log.returncode == 0 else None
        except Exception as e:
            log(f"Erreur git EBP_App: {e}", "ERROR")

    return result

def run_ebp_build() -> tuple:
    """Lance le build des sous-projets EBP_App (monorepo) et retourne (success, output)"""
    if not EBP_APP_DIR.exists():
        return False, "Projet non trouvé"

    log("🔨 Lancement build EBP_App (monorepo)...", "ACTION")

    # Structure monorepo: ebp-api, ebp-web, mobile
    subprojects = [
        ("ebp-api", EBP_APP_DIR / "ebp-api"),
        ("ebp-web", EBP_APP_DIR / "ebp-web"),
    ]

    results = []
    all_success = True

    for name, path in subprojects:
        if not path.exists() or not (path / "package.json").exists():
            log(f"⏭️ Skip {name} (pas de package.json)", "INFO")
            continue

        try:
            # Détecter package manager
            if (path / "pnpm-lock.yaml").exists():
                pm = "pnpm"
            elif (path / "yarn.lock").exists():
                pm = "yarn"
            else:
                pm = "npm"

            # Installer si pas de node_modules
            if not (path / "node_modules").exists():
                log(f"📦 Install {name}...", "ACTION")
                subprocess.run([pm, "install"], cwd=path, capture_output=True, timeout=180)

            # Build avec timeout court pour ne pas bloquer
            log(f"🔨 Build {name}...", "ACTION")
            build = subprocess.run(
                [pm, "run", "build"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=120  # 2min max par projet
            )

            if build.returncode == 0:
                log(f"✅ {name} build OK", "SUCCESS")
                results.append((name, True, "OK"))
            else:
                log(f"❌ {name} build FAIL", "ERROR")
                results.append((name, False, build.stderr[-200:]))
                all_success = False

        except subprocess.TimeoutExpired:
            log(f"⏱️ {name} timeout", "WARNING")
            results.append((name, False, "timeout"))
            all_success = False
        except Exception as e:
            log(f"❌ {name} erreur: {e}", "ERROR")
            results.append((name, False, str(e)[:100]))
            all_success = False

    summary = ", ".join([f"{n}:{'✓' if s else '✗'}" for n, s, _ in results])
    return all_success, summary

def run_ebp_lint() -> tuple:
    """Lance le lint du projet EBP_App"""
    if not EBP_APP_DIR.exists():
        return False, "Projet non trouvé"

    try:
        # Détecter package manager
        if (EBP_APP_DIR / "pnpm-lock.yaml").exists():
            pm = "pnpm"
        elif (EBP_APP_DIR / "yarn.lock").exists():
            pm = "yarn"
        else:
            pm = "npm"

        lint = subprocess.run(
            [pm, "run", "lint"],
            cwd=EBP_APP_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )

        return lint.returncode == 0, lint.stdout + lint.stderr
    except Exception as e:
        return False, str(e)

def run_ebp_improvement():
    """Lance une session d'amélioration du projet EBP_App"""
    log("🚀 Amélioration automatique EBP_App", "ACTION")

    # 1. Vérifier l'état du projet
    state = check_ebp_app_project()
    if not state["exists"]:
        log("Projet EBP_App non trouvé, skip amélioration", "WARNING")
        return

    log(f"📊 État EBP_App: changes={state['uncommitted_changes']}, last={state['last_commit']}")

    # 2. TOUJOURS vérifier que le build passe avant toute modification
    build_ok, build_output = run_ebp_build()
    if not build_ok:
        log(f"❌ Build initial échoué - pas d'amélioration automatique", "ERROR")
        # Sauvegarder l'erreur pour analyse
        error_file = LOGS_DIR / "ebp_build_error.log"
        error_file.write_text(f"Build Error {datetime.now()}\n{build_output}")
        return

    # 3. Vérifier le lint
    lint_ok, lint_output = run_ebp_lint()
    if not lint_ok:
        log("⚠️ Lint a des erreurs - noter pour correction", "WARNING")

    # 4. Lancer Claude pour amélioration si pas de changements non commités
    if not state["uncommitted_changes"]:
        improvement_prompt = f"""
Tu es Aura en mode auto-amélioration du projet EBP_App (mode watchdog automatique).
Le projet est dans: {EBP_APP_DIR}

RÈGLE ABSOLUE: Après CHAQUE modification, tu DOIS lancer le build et vérifier qu'il passe.
Commande build: cd {EBP_APP_DIR} && npm run build (ou pnpm/yarn selon le projet)

Tâches autorisées (choisis 1-2 max):
1. Corriger les erreurs de lint si présentes
2. Améliorer les types TypeScript (any → types concrets)
3. Ajouter des commentaires JSDoc manquants
4. Optimiser les imports (ordre, unused)
5. Petits refactoring safe (early returns, const, etc.)

INTERDIT:
- Changements de logique business
- Nouvelles features
- Suppressions de code fonctionnel
- Modifications sans vérifier le build

Après tes modifications:
1. Lance le build pour vérifier
2. Si build OK: fais un commit "chore: auto-improvement par Aura watchdog"
3. Si build KO: revert tes changements

Sois conservateur et prudent. Log tes actions.
"""
        try:
            result = subprocess.run(
                ["claude", "--print", "-p", improvement_prompt],
                capture_output=True,
                text=True,
                timeout=600,  # 10 min max
                cwd=str(EBP_APP_DIR)
            )

            if result.returncode == 0:
                log("✅ Session amélioration EBP_App terminée", "SUCCESS")
                # Vérification finale du build
                final_build, _ = run_ebp_build()
                if final_build:
                    log("✅ Build final OK", "SUCCESS")
                else:
                    log("❌ Build final KO - revert nécessaire", "ERROR")
            else:
                log(f"❌ Erreur amélioration: {result.stderr[:200]}", "ERROR")

        except subprocess.TimeoutExpired:
            log("⏱️ Timeout amélioration EBP_App (10min)", "WARNING")
        except Exception as e:
            log(f"❌ Exception amélioration: {e}", "ERROR")
    else:
        log("⚠️ Changements non commités détectés - skip amélioration auto", "WARNING")

def is_improvement_allowed() -> bool:
    """Vérifie si l'heure permet l'auto-amélioration (20h-5h seulement)"""
    hour = datetime.now().hour
    # Autorisé entre 20h (20) et 5h (5)
    # Donc: 20, 21, 22, 23, 0, 1, 2, 3, 4, 5
    return hour >= 20 or hour <= 5

def main():
    """Point d'entrée principal du watchdog"""
    log("=" * 50)
    log("🔍 AURA Watchdog - Vérification horaire", "START")

    # Vérifier si on est dans la plage horaire autorisée
    if not is_improvement_allowed():
        hour = datetime.now().hour
        log(f"⏰ Heure actuelle: {hour}h - Auto-amélioration désactivée (autorisée 20h-5h)", "INFO")
        log("→ Vérification simple sans amélioration")
        # Juste vérifier l'état, pas d'amélioration
        is_running = check_aura_running()
        if is_running:
            log("✅ Aura actif - tout va bien")
        else:
            log("💤 Aura inactif - amélioration reportée à ce soir")
        return 0

    # 1. Vérifie si Aura tourne déjà
    is_running = check_aura_running()
    has_recent_activity = check_recent_activity()

    if is_running:
        log("✅ Aura est actif - pas d'amélioration système")
        # Mais on vérifie quand même le projet EBP_App si pas de session active dessus
        log("→ Vérification projet EBP_App...")
        state = check_ebp_app_project()
        if state["exists"]:
            log(f"📊 EBP_App: dernier commit = {state['last_commit']}")
            # Juste vérifier le build, pas d'amélioration si utilisateur actif
            build_ok, _ = run_ebp_build()
            if not build_ok:
                log("⚠️ Build EBP_App en erreur - à vérifier", "WARNING")
        return 0

    if has_recent_activity:
        log("📊 Activité récente mais pas de processus actif")
        log("→ Lancement auto-amélioration légère")
        run_self_improvement()
        # Amélioration EBP_App aussi
        run_ebp_improvement()
        return 0

    # 2. Pas d'activité - lance une session complète
    log("💤 Aucune activité Aura depuis 1h+", "WARNING")
    log("→ Session auto-amélioration complète (Aura + EBP_App)")
    run_self_improvement()
    run_ebp_improvement()

    return 0

if __name__ == "__main__":
    sys.exit(main())
