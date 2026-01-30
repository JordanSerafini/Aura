#!/usr/bin/env python3
"""
AURA-OS Modernize Typing Script
Migre les imports typing legacy vers la syntaxe Python 3.10+
Team: core (maintenance)
"""

import argparse
import re
import sys
from pathlib import Path


# Mappings de remplacement
TYPING_REPLACEMENTS = {
    # Types génériques (PEP 585)
    r'\bList\[': 'list[',
    r'\bDict\[': 'dict[',
    r'\bSet\[': 'set[',
    r'\bTuple\[': 'tuple[',
    r'\bFrozenSet\[': 'frozenset[',
    r'\bType\[': 'type[',
    # Optional -> X | None (PEP 604)
    r'Optional\[([^\]]+)\]': r'\1 | None',
}

# Imports à supprimer si plus utilisés
LEGACY_IMPORTS = ['List', 'Dict', 'Set', 'Tuple', 'FrozenSet', 'Type', 'Optional', 'Union']


def modernize_file(filepath: Path, dry_run: bool = False) -> dict:
    """Modernise un fichier Python."""
    result = {
        'file': str(filepath),
        'changes': 0,
        'import_cleaned': False,
        'errors': []
    }

    try:
        content = filepath.read_text(encoding='utf-8')
        original = content

        # 1. Remplacer les types génériques
        for pattern, replacement in TYPING_REPLACEMENTS.items():
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                result['changes'] += len(re.findall(pattern, content))
                content = new_content

        # 2. Remplacer Union[X, Y] -> X | Y
        union_pattern = r'Union\[([^,\]]+),\s*([^\]]+)\]'
        while re.search(union_pattern, content):
            content = re.sub(union_pattern, r'\1 | \2', content)
            result['changes'] += 1

        # 3. Nettoyer les imports typing
        import_pattern = r'from typing import ([^\n]+)'
        match = re.search(import_pattern, content)
        if match:
            imports = [i.strip() for i in match.group(1).split(',')]
            # Garder seulement les imports encore nécessaires
            remaining = [i for i in imports if i not in LEGACY_IMPORTS or i in content.replace(match.group(0), '')]
            # Vérifier si chaque import legacy est encore utilisé
            remaining_clean = []
            for imp in remaining:
                imp_clean = imp.strip()
                if imp_clean in LEGACY_IMPORTS:
                    # Vérifier si vraiment utilisé (pas juste dans l'import)
                    test_content = content.replace(match.group(0), '')
                    if re.search(rf'\b{imp_clean}\b', test_content):
                        remaining_clean.append(imp_clean)
                else:
                    remaining_clean.append(imp_clean)

            if remaining_clean:
                new_import = f"from typing import {', '.join(remaining_clean)}"
                content = content.replace(match.group(0), new_import)
            else:
                # Supprimer complètement la ligne d'import
                content = re.sub(r'from typing import [^\n]+\n', '', content)
                result['import_cleaned'] = True

        # 4. Écrire si changements et pas dry_run
        if content != original:
            if not dry_run:
                filepath.write_text(content, encoding='utf-8')
            result['modified'] = True
        else:
            result['modified'] = False

    except Exception as e:
        result['errors'].append(str(e))

    return result


def modernize_directory(path: Path, dry_run: bool = False) -> list:
    """Modernise tous les fichiers Python d'un répertoire."""
    results = []

    for filepath in path.glob('*.py'):
        if filepath.name == 'modernize_typing.py':
            continue
        result = modernize_file(filepath, dry_run)
        if result['changes'] > 0 or result['import_cleaned']:
            results.append(result)

    return results


def print_report(results: list, dry_run: bool):
    """Affiche le rapport."""
    print(f"\n{'='*60}")
    print(f" Modernize Typing Report {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}\n")

    total_changes = 0
    for r in results:
        if r['changes'] > 0 or r['import_cleaned']:
            status = "DRY" if dry_run else "OK"
            print(f"  [{status}] {Path(r['file']).name}: {r['changes']} replacements")
            total_changes += r['changes']

    print(f"\n  Total: {len(results)} files, {total_changes} changes")

    if dry_run:
        print("\n  Run without --dry-run to apply changes.")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Modernize Python typing imports")
    parser.add_argument("path", nargs="?", default=".", help="Path to modernize")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changing")
    parser.add_argument("--file", help="Single file to modernize")

    args = parser.parse_args()

    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"File not found: {filepath}")
            sys.exit(1)
        results = [modernize_file(filepath, args.dry_run)]
    else:
        path = Path(args.path)
        if not path.exists():
            print(f"Path not found: {path}")
            sys.exit(1)
        results = modernize_directory(path, args.dry_run)

    print_report(results, args.dry_run)


if __name__ == "__main__":
    main()
