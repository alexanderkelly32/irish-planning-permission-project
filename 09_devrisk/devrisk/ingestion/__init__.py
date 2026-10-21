"""Structured ingestion: source snapshots -> raw (immutable) -> bronze Parquet."""
from __future__ import annotations

from . import bcms, npad, ppr

__all__ = ["bcms", "npad", "ppr"]
