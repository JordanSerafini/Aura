#!/usr/bin/env python3
"""
AURA-OS ML Inspector Agent
Inspection et analyse de modèles ML/DL
Team: core (ML workflows)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from datetime import datetime

# Imports conditionnels
ML_LIBS = {}

try:
    import sklearn
    ML_LIBS['sklearn'] = sklearn.__version__
except ImportError:
    pass

try:
    import torch
    ML_LIBS['pytorch'] = torch.__version__
except ImportError:
    pass

try:
    import tensorflow as tf
    ML_LIBS['tensorflow'] = tf.__version__
except ImportError:
    pass

try:
    import joblib
    ML_LIBS['joblib'] = True
except ImportError:
    pass

try:
    import pickle
    ML_LIBS['pickle'] = True
except ImportError:
    pass


def get_environment_info() -> dict[str, Any]:
    """Récupère les infos de l'environnement ML."""
    import platform
    import os

    env = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "ml_libraries": ML_LIBS,
        "gpu_available": False,
        "gpu_info": None
    }

    # Check GPU PyTorch
    if 'pytorch' in ML_LIBS:
        import torch
        env["gpu_available"] = torch.cuda.is_available()
        if env["gpu_available"]:
            env["gpu_info"] = {
                "device_count": torch.cuda.device_count(),
                "device_name": torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else None,
                "memory_total": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2) if torch.cuda.device_count() > 0 else None
            }

    return env


def inspect_sklearn_model(model) -> dict[str, Any]:
    """Inspecte un modèle scikit-learn."""
    info = {
        "type": "sklearn",
        "class": type(model).__name__,
        "module": type(model).__module__,
        "params": {},
        "fitted": False,
        "features": None
    }

    # Paramètres
    try:
        info["params"] = model.get_params()
    except:
        pass

    # Check si fitted
    try:
        if hasattr(model, 'feature_importances_'):
            info["fitted"] = True
            info["feature_importances"] = model.feature_importances_.tolist()[:20]
        elif hasattr(model, 'coef_'):
            info["fitted"] = True
            info["coefficients_shape"] = list(model.coef_.shape) if hasattr(model.coef_, 'shape') else None
        elif hasattr(model, 'cluster_centers_'):
            info["fitted"] = True
            info["n_clusters"] = len(model.cluster_centers_)
    except:
        pass

    # Nombre de features
    try:
        if hasattr(model, 'n_features_in_'):
            info["features"] = model.n_features_in_
    except:
        pass

    return info


def inspect_pytorch_model(model) -> dict[str, Any]:
    """Inspecte un modèle PyTorch."""
    import torch

    info = {
        "type": "pytorch",
        "class": type(model).__name__,
        "trainable_params": 0,
        "total_params": 0,
        "layers": [],
        "device": str(next(model.parameters()).device) if list(model.parameters()) else "cpu"
    }

    # Compter les paramètres
    for p in model.parameters():
        info["total_params"] += p.numel()
        if p.requires_grad:
            info["trainable_params"] += p.numel()

    # Lister les layers
    for name, module in model.named_modules():
        if name:
            info["layers"].append({
                "name": name,
                "type": type(module).__name__
            })

    info["layers"] = info["layers"][:30]

    return info


def load_and_inspect(filepath: Path) -> dict[str, Any | None]:
    """Charge et inspecte un modèle."""
    result = {
        "file": str(filepath),
        "size_mb": round(filepath.stat().st_size / 1024 / 1024, 2),
        "format": filepath.suffix,
        "loaded": False,
        "model_info": None,
        "error": None
    }

    try:
        if filepath.suffix in ['.pkl', '.pickle']:
            if 'joblib' in ML_LIBS:
                import joblib
                model = joblib.load(filepath)
            else:
                import pickle
                with open(filepath, 'rb') as f:
                    model = pickle.load(f)

            if hasattr(model, 'get_params'):
                result["model_info"] = inspect_sklearn_model(model)
            else:
                result["model_info"] = {"type": "unknown", "class": type(model).__name__}

            result["loaded"] = True

        elif filepath.suffix in ['.pt', '.pth']:
            if 'pytorch' in ML_LIBS:
                import torch
                data = torch.load(filepath, map_location='cpu')

                if isinstance(data, torch.nn.Module):
                    result["model_info"] = inspect_pytorch_model(data)
                elif isinstance(data, dict):
                    result["model_info"] = {
                        "type": "pytorch_state_dict",
                        "keys": list(data.keys())[:20],
                        "total_keys": len(data)
                    }
                result["loaded"] = True

        elif filepath.suffix == '.onnx':
            result["model_info"] = {
                "type": "onnx",
                "note": "ONNX model detected. Use onnx library for detailed inspection."
            }
            result["loaded"] = True

        elif filepath.suffix in ['.h5', '.keras']:
            if 'tensorflow' in ML_LIBS:
                import tensorflow as tf
                model = tf.keras.models.load_model(filepath, compile=False)
                result["model_info"] = {
                    "type": "keras",
                    "layers": len(model.layers),
                    "trainable_params": int(sum(tf.keras.backend.count_params(w) for w in model.trainable_weights)),
                    "total_params": int(model.count_params())
                }
                result["loaded"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


def scan_models(path: Path) -> dict[str, Any]:
    """Scan un répertoire pour trouver les modèles."""
    extensions = ['.pkl', '.pickle', '.joblib', '.pt', '.pth', '.onnx', '.h5', '.keras', '.pb']
    models = []

    exclude = ['node_modules', 'venv', '.venv', '__pycache__', '.git']

    for ext in extensions:
        for f in path.rglob(f'*{ext}'):
            if any(excl in str(f) for excl in exclude):
                continue
            try:
                models.append({
                    "path": str(f),
                    "name": f.name,
                    "format": ext,
                    "size_mb": round(f.stat().st_size / 1024 / 1024, 2)
                })
            except:
                pass

    return {
        "directory": str(path),
        "scanned_at": datetime.now().isoformat(),
        "total_models": len(models),
        "models": sorted(models, key=lambda x: x['size_mb'], reverse=True)
    }


def print_inspection(result: dict[str, Any]):
    """Affiche le résultat d'inspection."""
    print(f"\n{'='*60}")
    print(f" Model Inspection: {Path(result['file']).name}")
    print(f"{'='*60}\n")

    print(f" File Info:")
    print(f"   Size: {result['size_mb']} MB")
    print(f"   Format: {result['format']}")
    print(f"   Loaded: {'✅ Yes' if result['loaded'] else '❌ No'}")

    if result['error']:
        print(f"   Error: {result['error']}")

    if result['model_info']:
        info = result['model_info']
        print(f"\n Model Info:")
        print(f"   Type: {info.get('type', 'unknown')}")
        print(f"   Class: {info.get('class', 'N/A')}")

        if 'total_params' in info:
            print(f"   Total params: {info['total_params']:,}")
        if 'trainable_params' in info:
            print(f"   Trainable params: {info['trainable_params']:,}")
        if 'features' in info and info['features']:
            print(f"   Input features: {info['features']}")
        if 'fitted' in info:
            print(f"   Fitted: {'Yes' if info['fitted'] else 'No'}")
        if 'device' in info:
            print(f"   Device: {info['device']}")
        if 'layers' in info and isinstance(info['layers'], list):
            print(f"   Layers: {len(info['layers'])}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="AURA ML Inspector")
    parser.add_argument("path", nargs="?", default=".", help="Model file or directory")
    parser.add_argument("--env", action="store_true", help="Show ML environment info")
    parser.add_argument("--scan", action="store_true", help="Scan directory for models")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()
    path = Path(args.path).resolve()

    if args.env:
        env = get_environment_info()
        if args.json:
            print(json.dumps(env, indent=2))
        else:
            print(f"\n ML Environment:")
            print(f"   Python: {env['python_version']}")
            print(f"   Libraries: {', '.join(f'{k}={v}' for k, v in env['ml_libraries'].items() if v)}")
            print(f"   GPU: {'✅ Available' if env['gpu_available'] else '❌ Not available'}")
            if env['gpu_info']:
                print(f"   GPU Name: {env['gpu_info']['device_name']}")
                print(f"   GPU Memory: {env['gpu_info']['memory_total']} GB")
            print()
        return

    if args.scan or path.is_dir():
        result = scan_models(path)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\n Models in {result['directory']}:")
            print(f" Found {result['total_models']} model files\n")
            for m in result['models'][:15]:
                print(f"   {m['size_mb']:>8.2f} MB  {m['format']:<8} {m['name']}")
            print()
        return

    if path.is_file():
        result = load_and_inspect(path)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print_inspection(result)


if __name__ == "__main__":
    main()
