#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI


ROOT = Path(__file__).resolve().parents[2]


def load_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key

    env_path = ROOT / "openai_key.env"
    if env_path.exists():
        raw = env_path.read_text(encoding="utf-8").strip()
        if raw:
            return raw

    raise RuntimeError("OPENAI_API_KEY is not set and openai_key.env is missing or empty.")


def load_deepseek_api_key() -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if api_key:
        return api_key

    for env_path in (ROOT / "deepseek_key.env", ROOT / "deepseek_key.txt"):
        if env_path.exists():
            raw = env_path.read_text(encoding="utf-8").strip()
            if raw:
                return raw

    raise RuntimeError("DEEPSEEK_API_KEY is not set and no deepseek_key file is present.")


def make_client() -> OpenAI:
    return OpenAI(api_key=load_api_key())


def make_deepseek_client() -> OpenAI:
    return OpenAI(api_key=load_deepseek_api_key(), base_url="https://api.deepseek.com")
