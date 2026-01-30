#!/usr/bin/env python3
"""
AURA-OS Data Profiler Agent
Profilage et analyse qualité de données CSV/JSON/Parquet
Team: core (ML workflows)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

try:
    import pandas as pd
    import numpy as np
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


def profile_dataframe(df: pd.DataFrame, name: str = "dataset") -> Dict[str, Any]:
    """Profile complet d'un DataFrame."""
    profile = {
        "name": name,
        "rows": len(df),
        "columns": len(df.columns),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2),
        "columns_info": {},
        "quality_score": 100,
        "issues": [],
        "recommendations": []
    }

    total_cells = len(df) * len(df.columns)
    total_nulls = df.isnull().sum().sum()
    null_ratio = total_nulls / total_cells if total_cells > 0 else 0

    profile["null_percentage"] = round(null_ratio * 100, 2)
    profile["duplicate_rows"] = int(df.duplicated().sum())

    # Analyse par colonne
    for col in df.columns:
        col_info = {
            "dtype": str(df[col].dtype),
            "null_count": int(df[col].isnull().sum()),
            "null_pct": round(df[col].isnull().mean() * 100, 2),
            "unique_count": int(df[col].nunique()),
            "unique_pct": round(df[col].nunique() / len(df) * 100, 2) if len(df) > 0 else 0
        }

        # Stats numériques
        if pd.api.types.is_numeric_dtype(df[col]):
            col_info["mean"] = round(float(df[col].mean()), 4) if not df[col].isnull().all() else None
            col_info["std"] = round(float(df[col].std()), 4) if not df[col].isnull().all() else None
            col_info["min"] = float(df[col].min()) if not df[col].isnull().all() else None
            col_info["max"] = float(df[col].max()) if not df[col].isnull().all() else None

            # Détection outliers (IQR)
            if not df[col].isnull().all():
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                outliers = ((df[col] < Q1 - 1.5 * IQR) | (df[col] > Q3 + 1.5 * IQR)).sum()
                col_info["outliers"] = int(outliers)
                if outliers > len(df) * 0.05:
                    profile["issues"].append(f"Column '{col}': {outliers} outliers detected ({round(outliers/len(df)*100, 1)}%)")

        # Stats catégorielles
        elif pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_categorical_dtype(df[col]):
            top_values = df[col].value_counts().head(5).to_dict()
            col_info["top_values"] = {str(k): int(v) for k, v in top_values.items()}

            # Cardinality check
            if col_info["unique_pct"] > 90 and col_info["unique_count"] > 100:
                profile["issues"].append(f"Column '{col}': High cardinality ({col_info['unique_count']} unique values)")

        # Datetime
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            col_info["min_date"] = str(df[col].min())
            col_info["max_date"] = str(df[col].max())

        # Checks qualité
        if col_info["null_pct"] > 50:
            profile["issues"].append(f"Column '{col}': {col_info['null_pct']}% missing values")
            profile["quality_score"] -= 5

        if col_info["null_pct"] > 0 and col_info["null_pct"] <= 5:
            profile["recommendations"].append(f"Column '{col}': Consider imputation for {col_info['null_pct']}% missing values")

        profile["columns_info"][col] = col_info

    # Ajustement score qualité
    profile["quality_score"] -= min(30, int(null_ratio * 100))
    profile["quality_score"] -= min(10, profile["duplicate_rows"] // 100)
    profile["quality_score"] = max(0, profile["quality_score"])

    # Recommendations générales
    if profile["duplicate_rows"] > 0:
        profile["recommendations"].append(f"Consider removing {profile['duplicate_rows']} duplicate rows")

    if len(df.columns) > 50:
        profile["recommendations"].append("High dimensionality - consider feature selection")

    return profile


def load_data(filepath: Path) -> Optional[pd.DataFrame]:
    """Charge un fichier de données."""
    try:
        if filepath.suffix == '.csv':
            return pd.read_csv(filepath, nrows=100000)  # Limit pour perf
        elif filepath.suffix == '.json':
            return pd.read_json(filepath)
        elif filepath.suffix == '.parquet':
            return pd.read_parquet(filepath)
        elif filepath.suffix in ['.xlsx', '.xls']:
            return pd.read_excel(filepath)
        else:
            return None
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None


def print_profile(profile: Dict[str, Any], verbose: bool = False):
    """Affiche le profil formaté."""
    print(f"\n{'='*60}")
    print(f" Data Profile: {profile['name']}")
    print(f"{'='*60}\n")

    print(f" Overview:")
    print(f"   Rows: {profile['rows']:,}")
    print(f"   Columns: {profile['columns']}")
    print(f"   Memory: {profile['memory_mb']} MB")
    print(f"   Missing: {profile['null_percentage']}%")
    print(f"   Duplicates: {profile['duplicate_rows']:,}")
    print(f"   Quality Score: {profile['quality_score']}/100")

    if profile['issues']:
        print(f"\n Issues ({len(profile['issues'])}):")
        for issue in profile['issues'][:10]:
            print(f"   ⚠️  {issue}")

    if profile['recommendations']:
        print(f"\n Recommendations:")
        for rec in profile['recommendations'][:5]:
            print(f"   💡 {rec}")

    if verbose:
        print(f"\n Columns Detail:")
        for col, info in list(profile['columns_info'].items())[:15]:
            dtype = info['dtype']
            nulls = info['null_pct']
            uniq = info['unique_count']
            print(f"   {col[:25]:<25} {dtype:<15} {nulls:>5}% null  {uniq:>6} unique")

    print(f"\n{'='*60}\n")


def scan_directory(path: Path) -> Dict[str, Any]:
    """Scan un répertoire pour trouver les fichiers de données."""
    extensions = ['.csv', '.json', '.parquet', '.xlsx', '.xls']
    files = []

    for ext in extensions:
        for f in path.rglob(f'*{ext}'):
            if not any(excl in str(f) for excl in ['node_modules', 'venv', '.git', '__pycache__']):
                try:
                    size = f.stat().st_size / (1024 * 1024)  # MB
                    files.append({
                        "path": str(f),
                        "name": f.name,
                        "extension": ext,
                        "size_mb": round(size, 2)
                    })
                except:
                    pass

    return {
        "directory": str(path),
        "scanned_at": datetime.now().isoformat(),
        "total_files": len(files),
        "files": sorted(files, key=lambda x: x['size_mb'], reverse=True)[:20]
    }


def main():
    parser = argparse.ArgumentParser(description="AURA Data Profiler")
    parser.add_argument("path", nargs="?", default=".", help="File or directory to profile")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--scan", action="store_true", help="Scan directory for data files")

    args = parser.parse_args()

    if not PANDAS_AVAILABLE:
        print("Error: pandas is required. Install with: pip install pandas")
        sys.exit(1)

    path = Path(args.path).resolve()

    if args.scan or path.is_dir():
        result = scan_directory(path)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n Data Files in {result['directory']}:")
            print(f" Found {result['total_files']} files\n")
            for f in result['files'][:15]:
                print(f"   {f['size_mb']:>8.2f} MB  {f['name']}")
            print()

        # Si un seul fichier trouvé, le profiler
        if result['total_files'] == 1 and not args.scan:
            path = Path(result['files'][0]['path'])

    if path.is_file():
        df = load_data(path)
        if df is not None:
            profile = profile_dataframe(df, path.name)
            if args.json:
                print(json.dumps(profile, indent=2, default=str))
            else:
                print_profile(profile, args.verbose)
        else:
            print(f"Could not load: {path}")
            sys.exit(1)


if __name__ == "__main__":
    main()
