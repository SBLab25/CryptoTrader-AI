"""Embedding helpers with graceful local fallbacks."""

from __future__ import annotations

import hashlib
import os
import threading

EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024
MAX_TEXT_LENGTH = 512

_model_lock = threading.Lock()
_model = None


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(
                EMBEDDING_MODEL,
                cache_folder=os.getenv("HF_HOME", os.path.expanduser("~/.cache/huggingface")),
            )
        except Exception:
            _model = None
    return _model


def _build_signal_text(reasoning: str, indicators: dict, symbol: str, action: str, strategy: str) -> str:
    ind_text = _format_indicators(indicators)
    text = (
        f"Symbol: {symbol}. Strategy: {strategy}. Signal: {action}. "
        f"Market indicators: {ind_text}. Analysis: {reasoning}"
    )
    return text[: MAX_TEXT_LENGTH * 4]


def _build_indicator_text(indicators: dict, symbol: str) -> str:
    return f"Symbol: {symbol}. Current market indicators: {_format_indicators(indicators)}."


def _format_indicators(indicators: dict) -> str:
    parts: list[str] = []
    if (rsi := indicators.get("rsi")) is not None:
        parts.append(f"RSI {rsi:.1f}")
    if (macd_h := indicators.get("macd_histogram")) is not None:
        parts.append(f"MACD histogram {'positive' if macd_h > 0 else 'negative'} ({macd_h:.4f})")
    if (bb := indicators.get("bb_percent_b")) is not None:
        if bb < 0.2:
            parts.append(f"price near lower Bollinger Band ({bb:.2f})")
        elif bb > 0.8:
            parts.append(f"price near upper Bollinger Band ({bb:.2f})")
        else:
            parts.append(f"Bollinger Band position {bb:.2f}")
    if (trend := indicators.get("ema_trend")):
        parts.append(f"EMA trend {trend}")
    if (atr := indicators.get("atr")) is not None:
        parts.append(f"ATR {atr:.2f}")
    if (vol := indicators.get("volume_ratio")) is not None:
        if vol > 1.5:
            parts.append(f"high volume ({vol:.1f}x average)")
        elif vol < 0.7:
            parts.append(f"low volume ({vol:.1f}x average)")
    return ", ".join(parts) if parts else "no indicators"


def _hash_fallback_vector(text: str) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < EMBEDDING_DIM:
        digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
        values.extend(((byte / 255.0) * 2.0) - 1.0 for byte in digest)
        counter += 1
    return [float(v) for v in values[:EMBEDDING_DIM]]


def _encode(text: str) -> list[float]:
    model = _get_model()
    if model is None:
        return _hash_fallback_vector(text)
    vector = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return [float(v) for v in vector.tolist()]


def embed_signal(reasoning: str, indicators: dict, symbol: str = "", action: str = "", strategy: str = "") -> list[float]:
    return _encode(_build_signal_text(reasoning, indicators, symbol, action, strategy))


def embed_indicators(indicators: dict, symbol: str = "") -> list[float]:
    return _encode(_build_indicator_text(indicators, symbol))


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    if model is None:
        return [_hash_fallback_vector(text) for text in texts]
    arrays = model.encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=False)
    return [[float(v) for v in array.tolist()] for array in arrays]


def is_model_loaded() -> bool:
    return _model is not None


def get_model_info() -> dict:
    return {
        "model": EMBEDDING_MODEL,
        "dim": EMBEDDING_DIM,
        "loaded": is_model_loaded(),
        "device": str(getattr(_model, "device", "fallback")) if _model is not None else "fallback",
    }
