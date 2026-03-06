from __future__ import annotations

from typing import List


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
    """
    Split a long text into overlapping character-based chunks.

    This is a simple, deterministic chunker that works well for pre-tokenised
    document text. It avoids dependencies on tokenizers to keep the module
    lightweight and self-contained.

    Args:
        text: Input text to split.
        chunk_size: Target length (in characters) of each chunk.
        overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        List of text chunks (strings).
    """
    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")
    if overlap < 0:
        raise ValueError("overlap must be non-negative.")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    chunks: List[str] = []
    text_length = len(text)
    start = 0

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end == text_length:
            break

        # Move the window forward with the desired overlap.
        start = max(0, end - overlap)

    return chunks


__all__ = ["chunk_text"]

