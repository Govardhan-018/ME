"""
Embeddings via Ollama, with a graceful fallback.

If an embedding model is available (default `nomic-embed-text`; override with
JARVIS_EMBED_MODEL), semantic recall uses real vector cosine similarity. If the
model isn't pulled — or numpy isn't installed — recall silently degrades to
keyword/recency search. Nothing breaks; it just gets sharper once you run
`ollama pull nomic-embed-text`.
"""
from __future__ import annotations

import os
import struct
from typing import Optional

import requests

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("JARVIS_EMBED_MODEL", "nomic-embed-text")

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

_available: Optional[bool] = None


def available() -> bool:
    """True iff we can actually produce embeddings (model present + numpy)."""
    global _available
    if not HAVE_NUMPY:
        return False
    if _available is None:
        try:
            r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
            tags = {m.get("name", "") for m in r.json().get("models", [])}
            want = EMBED_MODEL.split(":")[0]
            _available = any(t.split(":")[0] == want for t in tags)
        except Exception:
            _available = False
    return _available


def embed(text: str) -> Optional[bytes]:
    """Return the embedding for `text` as packed float32 bytes, or None."""
    if not available() or not text.strip():
        return None
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/embeddings",
                          json={"model": EMBED_MODEL, "prompt": text}, timeout=30)
        r.raise_for_status()
        vec = r.json().get("embedding")
        if not vec:
            return None
        return struct.pack(f"{len(vec)}f", *vec)
    except Exception:
        return None


def cosine(a: Optional[bytes], b: Optional[bytes]) -> float:
    if not HAVE_NUMPY or not a or not b:
        return 0.0
    va = np.frombuffer(a, dtype=np.float32)
    vb = np.frombuffer(b, dtype=np.float32)
    if va.shape != vb.shape or va.size == 0:
        return 0.0
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))
