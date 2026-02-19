"""Fence-aware and table-aware message chunker for Discord's 2000-character limit.

Inspired by OpenClaw: never split inside a code block. If forced to split,
properly close and reopen the fence markers.

Tables (GitHub Flavored Markdown pipe-tables) are treated as atomic blocks:
the chunker walks back from any candidate split point to the start of the
enclosing table so that Discord can render the whole table in one message.
When a table is too large to fit in a single message, continuation chunks
receive the table header+separator prepended so each chunk renders as a
standalone table.
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
    4. Never split inside a markdown table block
    5. Respect max_chars limit per chunk
    6. If a table must be split, prepend its header to continuation chunks
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

    raw = [c for c in chunks if c.strip()]
    return _fix_table_continuations(raw)


def _fix_table_continuations(chunks: list[str]) -> list[str]:
    """Prepend the table header to any chunk that starts mid-table.

    When a large table is split across messages, continuation chunks start
    with data rows but no header.  Discord requires a header+separator in
    every message to render the table correctly.  This pass tracks the active
    table header across chunks and prepends it where needed.
    """
    result: list[str] = []
    current_header: str | None = None

    for chunk in chunks:
        if current_header and _is_table_continuation_chunk(chunk):
            chunk = current_header + chunk

        # Update the active header: keep it if this chunk ends mid-table,
        # clear it if the chunk ends outside a table.
        if _chunk_ends_in_table(chunk):
            new_header = _find_chunk_table_header(chunk)
            if new_header is not None:
                current_header = new_header
            # else: keep current_header (shouldn't happen if table is well-formed)
        else:
            current_header = None

        result.append(chunk)

    return result


def _find_split_point(text: str, max_chars: int) -> int:
    """Find the best position to split the text.

    Preference order:
    1. Paragraph break (blank line) before max_chars
    2. Line break before max_chars
    3. Hard split at max_chars

    After finding a candidate, the split is moved back to the start of any
    enclosing markdown table block so tables are never split mid-block.
    """
    search_region = text[:max_chars]

    # Search backward from max_chars for a blank line
    last_paragraph = search_region.rfind("\n\n")
    if last_paragraph > max_chars // 3:
        candidate = last_paragraph + 1
    else:
        # Search backward for any newline
        last_newline = search_region.rfind("\n")
        candidate = last_newline + 1 if last_newline > max_chars // 3 else max_chars

    # Don't split inside a markdown table block
    return _retreat_to_table_start(text, candidate)


def _is_table_line(line: str) -> bool:
    """Return True if *line* looks like a markdown table row.

    A table row must start **and** end with a pipe character (after stripping
    whitespace) and contain at least one character between the pipes.
    """
    stripped = line.strip()
    return len(stripped) >= 3 and stripped.startswith("|") and stripped.endswith("|")


def _is_separator_row(line: str) -> bool:
    """Return True if *line* is a GFM table separator row.

    Separator rows contain only pipes, dashes, spaces, and optional colons
    (for alignment).  Example: ``|---|:---:|---:|``
    """
    if not _is_table_line(line):
        return False
    inner = line.strip()[1:-1]  # strip outer pipes
    return all(c in "-: |" for c in inner)


def _chunk_ends_in_table(chunk: str) -> bool:
    """Return True if the last non-blank line of *chunk* is a table line."""
    for line in reversed(chunk.splitlines()):
        if line.strip():
            return _is_table_line(line)
    return False


def _find_chunk_table_header(chunk: str) -> str | None:
    """Return the header+separator string of the table that *chunk* ends in.

    Scans *chunk* forward to find the last complete header+separator pair
    belonging to the table that the chunk ends with.  Returns
    ``"header_row\\nsep_row\\n"`` or ``None`` if the table has no parseable
    header in this chunk.

    Only call this after confirming ``_chunk_ends_in_table(chunk)`` is True.
    """
    lines = chunk.splitlines()
    header_line: str | None = None
    sep_line: str | None = None

    for line in lines:
        if not _is_table_line(line):
            # Any non-table line (blank or text) marks a boundary between tables.
            # Reset tracking so the next table is treated as independent.
            header_line = None
            sep_line = None
            continue

        if _is_separator_row(line):
            if header_line is not None and sep_line is None:
                sep_line = line
        else:
            if sep_line is None:
                # Before we've seen the separator — this could be the header row
                header_line = line
            # After separator: data row; keep the captured header+sep

    if header_line and sep_line:
        return f"{header_line}\n{sep_line}\n"
    return None


def _is_table_continuation_chunk(chunk: str) -> bool:
    """Return True if *chunk* starts with table data rows but has no header.

    A "continuation chunk" is one produced by splitting a large table: it
    begins with rows that belong to the previous chunk's table but has no
    header+separator of its own.
    """
    lines = [ln for ln in chunk.splitlines() if ln.strip()]
    if not lines or not _is_table_line(lines[0]):
        return False

    # If the first table line is a separator, the header was in the previous chunk.
    if _is_separator_row(lines[0]):
        return True

    # First line is a data/header row.  A proper new table has a separator as
    # the second table line.  If we don't see one in the first few table lines,
    # this chunk is a continuation.
    table_lines_seen = 0
    for line in lines:
        if not _is_table_line(line):
            break
        table_lines_seen += 1
        if table_lines_seen == 1:
            continue  # skip the first (already checked above)
        # Second table line is also a data row → continuation (no separator found)
        return not _is_separator_row(line)

    # Only one table line found (or zero non-table lines after first)
    return True


def _retreat_to_table_start(text: str, split_pos: int) -> int:
    """If *split_pos* falls inside a markdown table block, return the position
    of the first character of that block.  Otherwise return *split_pos* unchanged.

    Ensures tables are kept intact so Discord can render them correctly.
    If the table starts at position 0 we cannot retreat further, so we return
    the original split_pos to avoid an infinite loop in the caller.
    """
    text_before = text[:split_pos]
    lines = text_before.split("\n")

    # Walk backwards, skipping any trailing blank lines
    i = len(lines) - 1
    while i >= 0 and not lines[i].strip():
        i -= 1

    # If the last non-blank line is not a table line, we're not inside a table
    if i < 0 or not _is_table_line(lines[i]):
        return split_pos

    # Walk further back to find the first line of the table block
    while i >= 0 and _is_table_line(lines[i]):
        i -= 1

    # i now points to the last line *before* the table
    table_first_line_idx = i + 1
    table_start_char = sum(len(lines[j]) + 1 for j in range(table_first_line_idx))

    if table_start_char == 0:
        # Table starts at the very beginning — cannot retreat, avoid infinite loop
        return split_pos

    return table_start_char


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
