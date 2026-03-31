"""Model context window lookup for SOMA."""

from __future__ import annotations

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # Anthropic
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    # OpenAI
    "gpt-4": 8_192,
    "gpt-4-turbo": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3": 200_000,
    "o3-mini": 200_000,
    # Default fallback
    "default": 200_000,
}


def get_context_window(model_name: str) -> int:
    """Look up context window size for a model.

    Strategy: exact match first, then prefix match, then default.
    """
    # Exact match
    if model_name in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model_name]

    # Prefix match: find the longest key that is a prefix of model_name
    best_match: str | None = None
    best_len = 0
    for key in MODEL_CONTEXT_WINDOWS:
        if key == "default":
            continue
        if model_name.startswith(key) and len(key) > best_len:
            best_match = key
            best_len = len(key)

    if best_match is not None:
        return MODEL_CONTEXT_WINDOWS[best_match]

    return MODEL_CONTEXT_WINDOWS["default"]


__all__ = ["MODEL_CONTEXT_WINDOWS", "get_context_window"]
