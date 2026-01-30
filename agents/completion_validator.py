#!/usr/bin/env python3
"""AURA Completion Validator Agent - Validates files before task completion."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

CONFIG_DIR = Path.home() / ".aura" / "hooks"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_DIR = Path.home() / "aura_logs"

DEFAULT_CONFIG = {
    "validators": {v: {"enabled": True} for v in
                   ["python", "javascript", "typescript", "yaml", "json", "file", "git"]},
    "skip_log": []
}

EXTENSION_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".yaml": "yaml",
    ".yml": "yaml", ".json": "json"
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            return json.load(open(CONFIG_FILE))
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    json.dump(config, open(CONFIG_FILE, "w"), indent=2)


def log_validation(vtype: str, path: str, success: bool, details: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"validation_{datetime.now().strftime('%Y%m%d')}.log"
    status = "PASS" if success else "FAIL"
    with open(log_file, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] [{vtype.upper()}] [{status}] {path} - {details}\n")


def print_result(success: bool, message: str) -> None:
    print(f"{'\u2705' if success else '\u274c'} {'PASS' if success else 'FAIL'}: {message}")


def run_cmd(cmd: list, cwd: Path = None) -> Tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def validate_python(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"File not found: {path}"
    rc, _, err = run_cmd([sys.executable, "-m", "py_compile", str(path)])
    if rc != 0:
        return False, f"Syntax error: {err}"
    test_file = path.parent / f"test_{path.name}"
    if test_file.exists():
        rc, out, _ = run_cmd([sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"])
        if rc != 0:
            return False, f"Tests failed: {out}"
        return True, "Syntax OK, tests passed"
    return True, "Syntax OK"


def validate_javascript(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"File not found: {path}"
    if subprocess.run(["which", "eslint"], capture_output=True).returncode == 0:
        rc, out, _ = run_cmd(["eslint", str(path)])
        return (True, "ESLint passed") if rc == 0 else (False, f"ESLint errors: {out}")
    if subprocess.run(["which", "node"], capture_output=True).returncode == 0:
        rc, _, err = run_cmd(["node", "--check", str(path)])
        return (True, "Syntax OK") if rc == 0 else (False, f"Syntax error: {err}")
    return True, "No JS validator available, skipped"


def validate_typescript(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"File not found: {path}"
    if subprocess.run(["which", "tsc"], capture_output=True).returncode == 0:
        rc, out, err = run_cmd(["tsc", "--noEmit", str(path)])
        return (True, "TypeScript OK") if rc == 0 else (False, f"TS errors: {err or out}")
    return validate_javascript(path)


def validate_yaml(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"File not found: {path}"
    try:
        import yaml
        yaml.safe_load(open(path))
        return True, "YAML syntax valid"
    except ImportError:
        return True, "PyYAML not installed, skipped"
    except Exception as e:
        return False, f"YAML error: {e}"


def validate_json(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"File not found: {path}"
    try:
        json.load(open(path))
        return True, "JSON syntax valid"
    except json.JSONDecodeError as e:
        return False, f"JSON error: {e}"


def validate_file(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"File not found: {path}"
    if not path.is_file():
        return False, f"Not a file: {path}"
    if path.stat().st_size == 0:
        return False, f"File is empty: {path}"
    if not os.access(path, os.R_OK):
        return False, f"File not readable: {path}"
    return True, f"File OK (size: {path.stat().st_size} bytes)"


def validate_git(path: Path) -> Tuple[bool, str]:
    git_root = path if path.is_dir() else path.parent
    while git_root != git_root.parent:
        if (git_root / ".git").exists():
            break
        git_root = git_root.parent
    else:
        return True, "Not a git repository, skipped"
    if not (git_root / ".pre-commit-config.yaml").exists():
        return True, "No .pre-commit-config.yaml, skipped"
    if subprocess.run(["which", "pre-commit"], capture_output=True).returncode != 0:
        return True, "pre-commit not installed, skipped"
    rc, out, _ = run_cmd(["pre-commit", "run", "--files", str(path)], cwd=git_root)
    return (True, "Pre-commit passed") if rc == 0 else (False, f"Pre-commit failed: {out}")


VALIDATORS = {
    "python": validate_python, "javascript": validate_javascript,
    "typescript": validate_typescript, "yaml": validate_yaml,
    "json": validate_json, "file": validate_file, "git": validate_git
}


def cmd_validate(args) -> int:
    config = load_config()
    vtype = args.type.lower()
    path = Path(args.path).resolve()
    if vtype not in VALIDATORS:
        print(f"\u274c Unknown validator: {vtype}")
        return 1
    if not config["validators"].get(vtype, {}).get("enabled", True):
        print(f"\u26a0\ufe0f Validator '{vtype}' is disabled")
        return 0
    success, details = VALIDATORS[vtype](path)
    print_result(success, f"[{vtype.upper()}] {path.name} - {details}")
    log_validation(vtype, str(path), success, details)
    return 0 if success else 1


def cmd_validate_auto(args) -> int:
    path = Path(args.path).resolve()
    success, details = validate_file(path)
    if not success:
        print_result(False, f"[FILE] {path.name} - {details}")
        log_validation("file", str(path), False, details)
        return 1
    detected = EXTENSION_MAP.get(path.suffix.lower())
    if detected and load_config()["validators"].get(detected, {}).get("enabled", True):
        success, details = VALIDATORS[detected](path)
        print_result(success, f"[{detected.upper()}] {path.name} - {details}")
        log_validation(detected, str(path), success, details)
        return 0 if success else 1
    print_result(True, f"[FILE] {path.name} - File validation passed")
    log_validation("file", str(path), True, "File validation passed")
    return 0


def cmd_configure(args) -> int:
    config = load_config()
    vtype = args.type.lower()
    enabled = args.enabled.lower() == "true"
    if vtype not in VALIDATORS:
        print(f"\u274c Unknown validator: {vtype}")
        return 1
    config["validators"].setdefault(vtype, {})["enabled"] = enabled
    save_config(config)
    print(f"\u2705 Validator '{vtype}' {'enabled' if enabled else 'disabled'}")
    return 0


def cmd_list_validators(args) -> int:
    config = load_config()
    print("Available validators:\n" + "-" * 40)
    for name in VALIDATORS:
        enabled = config["validators"].get(name, {}).get("enabled", True)
        print(f"  {name:<12} {'\u2705 enabled' if enabled else '\u274c disabled'}")
    return 0


def cmd_skip(args) -> int:
    config = load_config()
    config["skip_log"].append({"timestamp": datetime.now().isoformat(), "reason": args.reason})
    save_config(config)
    log_validation("SKIP", "N/A", True, f"Skipped: {args.reason}")
    print(f"\u26a0\ufe0f Validation skipped: {args.reason}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="AURA Completion Validator")
    subs = parser.add_subparsers(dest="command", help="Commands")

    p = subs.add_parser("validate", help="Validate with specific type")
    p.add_argument("--type", "-t", required=True, help="Validator type")
    p.add_argument("--path", "-p", required=True, help="File path")
    p.set_defaults(func=cmd_validate)

    p = subs.add_parser("validate-auto", help="Auto-detect and validate")
    p.add_argument("path", help="File path")
    p.set_defaults(func=cmd_validate_auto)

    p = subs.add_parser("configure", help="Configure validators")
    p.add_argument("--type", "-t", required=True, help="Validator type")
    p.add_argument("--enabled", "-e", required=True, help="true/false")
    p.set_defaults(func=cmd_configure)

    p = subs.add_parser("list-validators", help="List validators")
    p.set_defaults(func=cmd_list_validators)

    p = subs.add_parser("skip", help="Skip validation")
    p.add_argument("--reason", "-r", required=True, help="Skip reason")
    p.set_defaults(func=cmd_skip)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
