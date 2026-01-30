#!/usr/bin/env python3
"""
AURA Cache Manager - Gestion centralisée du cache pour tous les agents
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Any, Optional, Dict

CACHE_DIR = Path("/tmp/aura_cache")
CACHE_DIR.mkdir(exist_ok=True)

def _get_cache_file(key: str) -> Path:
    safe_key = hashlib.md5(key.encode()).hexdigest()[:16]
    return CACHE_DIR / f"aura_{key}_{safe_key}.json"

def get_cached(key: str, max_age_seconds: int = 300) -> Optional[Any]:
    cache_file = _get_cache_file(key)
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)
        if time.time() - data.get('_cached_at', 0) > max_age_seconds:
            return None
        return data.get('_data')
    except:
        return None

def set_cache(key: str, data: Any) -> bool:
    try:
        with open(_get_cache_file(key), 'w') as f:
            json.dump({'_cached_at': time.time(), '_key': key, '_data': data}, f)
        return True
    except:
        return False

def is_cache_valid(key: str, max_age_seconds: int = 300) -> bool:
    return get_cached(key, max_age_seconds) is not None

def clear_cache(key: Optional[str] = None) -> int:
    deleted = 0
    if key:
        f = _get_cache_file(key)
        if f.exists():
            f.unlink()
            deleted = 1
    else:
        for f in CACHE_DIR.glob("aura_*.json"):
            f.unlink()
            deleted += 1
    return deleted

def get_cache_info(key: str) -> Dict[str, Any]:
    cache_file = _get_cache_file(key)
    info = {'key': key, 'exists': cache_file.exists(), 'valid': False}
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            age = time.time() - data.get('_cached_at', 0)
            info['age_seconds'] = round(age, 1)
            info['valid'] = age <= 300
        except:
            pass
    return info

def list_caches() -> list:
    caches = []
    for f in CACHE_DIR.glob("aura_*.json"):
        try:
            with open(f) as file:
                data = json.load(file)
            caches.append({
                'key': data.get('_key', 'unknown'),
                'age': round(time.time() - data.get('_cached_at', 0), 1)
            })
        except:
            pass
    return caches
