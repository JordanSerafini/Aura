#!/home/tinkerbell/.aura/venv/bin/python3
"""
AURA Event Watcher Agent
Surveillance evenementielle avec watchdog pour detecter les changements de fichiers.
Supporte les regles personnalisees avec patterns glob et actions automatiques.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
except ImportError:
    print("Error: watchdog library not installed. Run: pip install watchdog")
    sys.exit(1)

# --- Configuration ---
HOME = Path.home()
AURA_DIR = HOME / ".aura"
TRIGGERS_DIR = AURA_DIR / "triggers"
RULES_FILE = TRIGGERS_DIR / "rules.json"
PID_FILE = TRIGGERS_DIR / "watcher.pid"
AGENTS_DIR = AURA_DIR / "agents"

def get_log_file() -> Path:
    """Get today's log file path."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_dir = HOME / "aura_logs" / today
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "triggers.md"

def log_event(message: str, level: str = "INFO") -> None:
    """Log an event to the daily log file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_file = get_log_file()

    if not log_file.exists():
        with open(log_file, 'w') as f:
            f.write(f"# Event Watcher Logs - {datetime.now().strftime('%Y-%m-%d')}\n\n")

    with open(log_file, 'a') as f:
        f.write(f"- **[{timestamp}]** `{level}`: {message}\n")

# --- Default Rules ---
DEFAULT_RULES = [
    {
        "id": "default-downloads",
        "path": str(HOME / "Downloads"),
        "pattern": "*.*",
        "event": "create",
        "action": f"{AGENTS_DIR}/file_organizer.py organize --path {{file}}",
        "enabled": True,
        "description": "Organize new downloads automatically"
    },
    {
        "id": "default-screenshots",
        "path": str(HOME / "Pictures/Screenshots"),
        "pattern": "*.png",
        "event": "create",
        "action": f"{AGENTS_DIR}/screenshot_ocr.py process --file {{file}}",
        "enabled": True,
        "description": "OCR new screenshots"
    },
    {
        "id": "default-aura-backup",
        "path": str(AURA_DIR),
        "pattern": "*.md",
        "event": "modify",
        "action": f"cp {{file}} {AURA_DIR}/backups/$(basename {{file}}).bak",
        "enabled": True,
        "description": "Backup AURA markdown files"
    }
]

# --- Rules Management ---
def load_rules() -> list:
    """Load rules from JSON file."""
    if not RULES_FILE.exists():
        save_rules(DEFAULT_RULES)
        return DEFAULT_RULES

    try:
        with open(RULES_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return DEFAULT_RULES

def save_rules(rules: list) -> None:
    """Save rules to JSON file."""
    TRIGGERS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RULES_FILE, 'w') as f:
        json.dump(rules, f, indent=2)

def add_rule(path: str, event: str, action: str, pattern: str = "*.*", description: str = "") -> dict:
    """Add a new rule."""
    rules = load_rules()
    rule_id = f"rule-{uuid.uuid4().hex[:8]}"

    new_rule = {
        "id": rule_id,
        "path": str(Path(path).expanduser().resolve()),
        "pattern": pattern,
        "event": event,
        "action": action,
        "enabled": True,
        "description": description or f"Watch {path} for {event} events"
    }

    rules.append(new_rule)
    save_rules(rules)
    log_event(f"Added rule: {rule_id} - {path} ({event})")
    return new_rule

def remove_rule(rule_id: str) -> bool:
    """Remove a rule by ID."""
    rules = load_rules()
    original_len = len(rules)
    rules = [r for r in rules if r["id"] != rule_id]

    if len(rules) < original_len:
        save_rules(rules)
        log_event(f"Removed rule: {rule_id}")
        return True
    return False

# --- Event Handler ---
class AuraEventHandler(FileSystemEventHandler):
    """Custom event handler for AURA rules."""

    def __init__(self, rules: list):
        super().__init__()
        self.rules = rules
        self.cooldown = {}  # Prevent duplicate triggers
        self.cooldown_seconds = 2

    def _check_cooldown(self, file_path: str, event_type: str) -> bool:
        """Check if event is in cooldown period."""
        key = f"{file_path}:{event_type}"
        now = time.time()

        if key in self.cooldown:
            if now - self.cooldown[key] < self.cooldown_seconds:
                return False

        self.cooldown[key] = now
        return True

    def _match_rule(self, file_path: str, event_type: str) -> dict | None:
        """Find matching rule for file and event type."""
        file_path = Path(file_path)

        for rule in self.rules:
            if not rule.get("enabled", True):
                continue

            rule_path = Path(rule["path"])
            rule_event = rule["event"]
            pattern = rule.get("pattern", "*.*")

            # Check event type
            if rule_event != event_type:
                continue

            # Check if file is in watched directory
            try:
                file_path.relative_to(rule_path)
            except ValueError:
                continue

            # Check pattern match
            if fnmatch(file_path.name, pattern):
                return rule

        return None

    def _execute_action(self, rule: dict, file_path: str) -> None:
        """Execute the action for a matched rule."""
        action = rule["action"].replace("{file}", str(file_path))

        log_event(f"Triggered rule '{rule['id']}' for {file_path}")

        try:
            # Execute in background
            subprocess.Popen(
                action,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            log_event(f"Executed action: {action}")
        except Exception as e:
            log_event(f"Error executing action: {e}", "ERROR")

    def _handle_event(self, event: FileSystemEvent, event_type: str) -> None:
        """Handle a file system event."""
        if event.is_directory:
            return

        file_path = event.src_path

        if not self._check_cooldown(file_path, event_type):
            return

        rule = self._match_rule(file_path, event_type)
        if rule:
            self._execute_action(rule, file_path)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "create")

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "modify")

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._handle_event(event, "delete")

# --- Daemon Management ---
def is_running() -> int | None:
    """Check if daemon is running, return PID if so."""
    if not PID_FILE.exists():
        return None

    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())

        # Check if process exists
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return None

def start_daemon() -> None:
    """Start the event watcher daemon."""
    if is_running():
        print("Event watcher is already running.")
        return

    # Fork to create daemon
    pid = os.fork()
    if pid > 0:
        print(f"Event watcher started (PID: {pid})")
        return

    # Decouple from parent
    os.setsid()
    os.umask(0)

    # Second fork
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Write PID file
    TRIGGERS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    # Setup signal handlers
    def cleanup(signum, frame):
        PID_FILE.unlink(missing_ok=True)
        log_event("Event watcher stopped")
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Redirect standard file descriptors
    sys.stdin = open(os.devnull, 'r')
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')

    # Start watching
    log_event("Event watcher started")
    run_watcher()

def run_watcher() -> None:
    """Run the file system watcher."""
    rules = load_rules()
    handler = AuraEventHandler(rules)
    observer = Observer()

    # Get unique paths to watch
    watched_paths = set()
    for rule in rules:
        if rule.get("enabled", True):
            path = Path(rule["path"])
            if path.exists():
                watched_paths.add(str(path))

    if not watched_paths:
        log_event("No valid paths to watch", "WARNING")
        return

    for path in watched_paths:
        observer.schedule(handler, path, recursive=False)
        log_event(f"Watching: {path}")

    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()

def stop_daemon() -> None:
    """Stop the event watcher daemon."""
    pid = is_running()
    if not pid:
        print("Event watcher is not running.")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Event watcher stopped (PID: {pid})")
        log_event("Event watcher stopped by user")
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        print("Event watcher process not found, cleaned up PID file.")

def show_status() -> None:
    """Show daemon status."""
    pid = is_running()
    rules = load_rules()
    active_rules = [r for r in rules if r.get("enabled", True)]

    print("=" * 50)
    print("AURA Event Watcher Status")
    print("=" * 50)

    if pid:
        print(f"Status: RUNNING (PID: {pid})")
    else:
        print("Status: STOPPED")

    print(f"\nTotal rules: {len(rules)}")
    print(f"Active rules: {len(active_rules)}")

    if active_rules:
        print("\nActive rules:")
        for rule in active_rules:
            print(f"  - {rule['id']}: {rule['path']}/{rule.get('pattern', '*.*')} ({rule['event']})")

def list_rules() -> None:
    """List all rules."""
    rules = load_rules()

    print("=" * 60)
    print("Event Watcher Rules")
    print("=" * 60)

    if not rules:
        print("No rules defined.")
        return

    for rule in rules:
        status = "ENABLED" if rule.get("enabled", True) else "DISABLED"
        print(f"\nID: {rule['id']}")
        print(f"  Path: {rule['path']}")
        print(f"  Pattern: {rule.get('pattern', '*.*')}")
        print(f"  Event: {rule['event']}")
        print(f"  Action: {rule['action']}")
        print(f"  Status: {status}")
        if rule.get("description"):
            print(f"  Description: {rule['description']}")

def test_path(path: str) -> None:
    """Test if a path matches any rules."""
    path = Path(path).expanduser().resolve()
    rules = load_rules()

    print(f"Testing path: {path}")
    print("-" * 40)

    matched = False
    for event_type in ["create", "modify", "delete"]:
        for rule in rules:
            if not rule.get("enabled", True):
                continue

            rule_path = Path(rule["path"])
            pattern = rule.get("pattern", "*.*")

            try:
                path.relative_to(rule_path)
                if fnmatch(path.name, pattern) and rule["event"] == event_type:
                    print(f"MATCH: Rule '{rule['id']}' ({event_type})")
                    print(f"  Action: {rule['action'].replace('{file}', str(path))}")
                    matched = True
            except ValueError:
                continue

    if not matched:
        print("No matching rules found.")

# --- Main Entry Point ---
def main():
    parser = argparse.ArgumentParser(
        description="AURA Event Watcher - File system event monitoring agent",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    subparsers.add_parser("start", help="Start the event watcher daemon")

    # Stop command
    subparsers.add_parser("stop", help="Stop the event watcher daemon")

    # Status command
    subparsers.add_parser("status", help="Show daemon status")

    # Add rule command
    add_parser = subparsers.add_parser("add-rule", help="Add a new watch rule")
    add_parser.add_argument("--path", required=True, help="Path to watch")
    add_parser.add_argument("--event", required=True, choices=["create", "modify", "delete"])
    add_parser.add_argument("--action", required=True, help="Command to execute")
    add_parser.add_argument("--pattern", default="*.*", help="Glob pattern (default: *.*)")
    add_parser.add_argument("--description", default="", help="Rule description")

    # Remove rule command
    remove_parser = subparsers.add_parser("remove-rule", help="Remove a watch rule")
    remove_parser.add_argument("--id", required=True, help="Rule ID to remove")

    # List rules command
    subparsers.add_parser("list-rules", help="List all watch rules")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test a path against rules")
    test_parser.add_argument("--path", required=True, help="Path to test")

    args = parser.parse_args()

    if args.command == "start":
        start_daemon()
    elif args.command == "stop":
        stop_daemon()
    elif args.command == "status":
        show_status()
    elif args.command == "add-rule":
        rule = add_rule(args.path, args.event, args.action, args.pattern, args.description)
        print(f"Rule added: {rule['id']}")
    elif args.command == "remove-rule":
        if remove_rule(args.id):
            print(f"Rule removed: {args.id}")
        else:
            print(f"Rule not found: {args.id}")
    elif args.command == "list-rules":
        list_rules()
    elif args.command == "test":
        test_path(args.path)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
