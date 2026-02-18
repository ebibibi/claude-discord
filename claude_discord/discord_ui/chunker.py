"""Fence-aware message chunker for Discord's 2000-character limit.

Inspired by OpenClaw: never split inside a code block. If forced to split,
properly close and reopen the fence markers.
"""

from __future__ import annotations

DISCORD_MAX_CHARS = 2000
# Leave room for fence reopening overhead
EFFECTIVE_MAX = DISCORD_MAX_CHARS - 50


def chunk_message(text: str, max_chars: int = EFFECTIVE_MAX) -> list[str]:
    """Split a message into Discord-safe chunks.

    Rules:
    1. Prefer splitting at paragraph boundaries (blank lines)
    2. Never split inside a code fence if possible
    3. If forced to split inside a fence, close it and reopen in next chunk
    4. Respect max_chars limit per chunk
    """
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Find a good split point
        split_at = _find_split_point(remaining, max_chars)
        chunk = remaining[:split_at].rstrip()
        remaining = remaining[split_at:].lstrip("\n")

        # Handle fence state
        chunk, fence_lang = _close_open_fence(chunk)
        chunks.append(chunk)

        # Reopen fence in next chunk if needed
        if fence_lang is not None:
            remaining = f"```{fence_lang}\n{remaining}"

    return [c for c in chunks if c.strip()]


def _find_split_point(text: str, max_chars: int) -> int:
    """Find the best position to split the text.

    Preference order:
    1. Paragraph break (blank line) before max_chars
    2. Line break before max_chars
    3. Hard split at max_chars
    """
    # Look for paragraph break
    search_region = text[:max_chars]

    # Search backward from max_chars for a blank line
    last_paragraph = search_region.rfind("\n\n")
    if last_paragraph > max_chars // 3:
        return last_paragraph + 1

    # Search backward for any newline
    last_newline = search_region.rfind("\n")
    if last_newline > max_chars // 3:
        return last_newline + 1

    # Hard split at max_chars
    return max_chars


def _close_open_fence(chunk: str) -> tuple[str, str | None]:
    """If the chunk has an unclosed code fence, close it.

    Returns:
        Tuple of (possibly modified chunk, fence language or None).
        fence language is None if no fence was open, "" if no language specified.
    """
    fence_count = 0
    fence_lang = ""
    lines = chunk.split("\n")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if fence_count % 2 == 0:
                # Opening fence
                fence_lang = stripped[3:].strip()
                fence_count += 1
            else:
                # Closing fence
                fence_count += 1

    # If odd number of fences, the last one is unclosed
    if fence_count % 2 == 1:
        return chunk + "\n```", fence_lang

    return chunk, None
