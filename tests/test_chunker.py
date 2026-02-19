"""Tests for fence-aware message chunker."""

from claude_discord.discord_ui.chunker import (
    _chunk_ends_in_table,
    _close_open_fence,
    _find_chunk_table_header,
    _is_separator_row,
    _is_table_continuation_chunk,
    _is_table_line,
    chunk_message,
)


class TestChunkMessage:
    def test_short_message_no_split(self):
        text = "Hello world"
        chunks = chunk_message(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_message(self):
        chunks = chunk_message("")
        assert chunks == []

    def test_splits_at_paragraph(self):
        text = "A" * 500 + "\n\n" + "B" * 500
        chunks = chunk_message(text, max_chars=600)
        assert len(chunks) == 2
        assert chunks[0].strip().startswith("A")
        assert chunks[1].strip().startswith("B")

    def test_splits_at_newline(self):
        text = "A" * 500 + "\n" + "B" * 500
        chunks = chunk_message(text, max_chars=600)
        assert len(chunks) == 2

    def test_hard_split(self):
        text = "A" * 2000
        chunks = chunk_message(text, max_chars=800)
        assert len(chunks) >= 2
        total = sum(len(c) for c in chunks)
        assert total == 2000

    def test_preserves_code_fence(self):
        text = "Before\n```python\n" + "x = 1\n" * 200 + "```\nAfter"
        chunks = chunk_message(text, max_chars=500)
        assert len(chunks) >= 2
        for i, chunk in enumerate(chunks):
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0, f"Chunk {i} has unbalanced fences: {fence_count}"

    def test_no_empty_chunks(self):
        text = "Hello\n\n\n\nWorld"
        chunks = chunk_message(text, max_chars=10)
        assert all(c.strip() for c in chunks)


TABLE_3ROW = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"


class TestIsTableLine:
    def test_table_row(self):
        assert _is_table_line("| Col1 | Col2 |")

    def test_separator_row(self):
        assert _is_table_line("|------|------|")

    def test_not_table(self):
        assert not _is_table_line("Just a normal line")

    def test_empty_line(self):
        assert not _is_table_line("")

    def test_partial_pipe_only_start(self):
        assert not _is_table_line("| only starts with pipe")


class TestTableChunking:
    def test_table_not_split(self):
        """A table that fits within a single chunk must not be split."""
        text = "Intro paragraph.\n\n" + TABLE_3ROW
        chunks = chunk_message(text)
        assert any(TABLE_3ROW in chunk for chunk in chunks)

    def test_splits_before_table(self):
        """Long preamble followed by a table: split before the table, not inside it."""
        # 880 + "\n\n" (2) + table (~38) = ~920 > max_chars=900
        preamble = "X" * 880
        text = preamble + "\n\n" + TABLE_3ROW
        chunks = chunk_message(text, max_chars=900)
        assert len(chunks) >= 2
        assert any(TABLE_3ROW in chunk for chunk in chunks)

    def test_table_at_message_start(self):
        """Table at the very start is returned intact if it fits."""
        text = TABLE_3ROW + "\n\nTrailing text."
        chunks = chunk_message(text)
        assert any(TABLE_3ROW in chunk for chunk in chunks)

    def test_header_and_separator_in_same_chunk(self):
        """Header and separator rows must never end up in different chunks."""
        header = "| Col |\n|-----|\n"
        many_rows = "| val |\n" * 300  # ~2400 chars — forces multiple splits
        text = header + many_rows
        chunks = chunk_message(text, max_chars=500)
        for chunk in chunks:
            lines = [ln for ln in chunk.splitlines() if _is_table_line(ln)]
            if not lines:
                continue
            # A separator-only row as the first table line means the header
            # ended up in a previous chunk — Discord cannot render that.
            first_cell = lines[0].replace("|", "").replace("-", "").replace(" ", "")
            assert first_cell != "", f"Chunk starts with separator row (no header): {chunk[:120]!r}"


HEADER_ROW = "| Feature | Status | Notes |"
SEP_ROW = "|---------|--------|-------|"
TABLE_HEADER = f"{HEADER_ROW}\n{SEP_ROW}\n"


class TestIsSeparatorRow:
    def test_simple_separator(self):
        assert _is_separator_row("|---|---|")

    def test_separator_with_spaces(self):
        assert _is_separator_row("| --- | --- |")

    def test_alignment_colons(self):
        assert _is_separator_row("|:---|---:|:---:|")

    def test_data_row_not_separator(self):
        assert not _is_separator_row("| val | ok |")

    def test_header_row_not_separator(self):
        assert not _is_separator_row("| Col1 | Col2 |")

    def test_non_table_line(self):
        assert not _is_separator_row("just text")


class TestChunkEndsInTable:
    def test_ends_in_table(self):
        chunk = "Some text.\n\n| Col |\n|-----|\n| val |"
        assert _chunk_ends_in_table(chunk)

    def test_ends_outside_table(self):
        chunk = "| Col |\n|-----|\n| val |\n\nSome text."
        assert not _chunk_ends_in_table(chunk)

    def test_empty_chunk(self):
        assert not _chunk_ends_in_table("")


class TestFindChunkTableHeader:
    def test_finds_header(self):
        chunk = f"{TABLE_HEADER}| item1 | ok | note1 |\n| item2 | ok | note2 |"
        result = _find_chunk_table_header(chunk)
        assert result == TABLE_HEADER

    def test_returns_none_when_chunk_ends_outside_table(self):
        chunk = f"{TABLE_HEADER}| item1 | ok | note1 |\n\nSome trailing text."
        result = _find_chunk_table_header(chunk)
        assert result is None

    def test_multiple_tables_returns_last(self):
        table1 = "| A |\n|---|\n| 1 |"
        table2 = "| B | C |\n|---|---|\n| 2 | 3 |"
        chunk = f"{table1}\n\n{table2}\n| 4 | 5 |"  # chunk ends in table2
        result = _find_chunk_table_header(chunk)
        assert result == "| B | C |\n|---|---|\n"


class TestIsTableContinuationChunk:
    def test_data_rows_only_is_continuation(self):
        chunk = "| item35 | ok | note35 |\n| item36 | ok | note36 |"
        assert _is_table_continuation_chunk(chunk)

    def test_separator_first_is_continuation(self):
        chunk = "|---|---|\n| val |"
        assert _is_table_continuation_chunk(chunk)

    def test_proper_header_not_continuation(self):
        chunk = f"{TABLE_HEADER}| item1 | ok | note1 |"
        assert not _is_table_continuation_chunk(chunk)

    def test_non_table_chunk_not_continuation(self):
        chunk = "Just some regular text here."
        assert not _is_table_continuation_chunk(chunk)


class TestTableContinuationChunks:
    """Tests for the _fix_table_continuations behaviour in chunk_message."""

    def _build_large_table(self, n_rows: int) -> str:
        rows = "".join(f"| item{j:03d} | ok | note{j:03d} |\n" for j in range(n_rows))
        return TABLE_HEADER + rows

    def test_large_table_all_chunks_have_header(self):
        """Every chunk that contains table content must start with header+sep."""
        table = self._build_large_table(80)  # > 1950 chars, forces multiple splits
        chunks = chunk_message("Summary:\n\n" + table)
        assert len(chunks) >= 2, "Expected at least 2 chunks for large table"

        for i, chunk in enumerate(chunks):
            table_lines = [ln for ln in chunk.splitlines() if _is_table_line(ln)]
            if not table_lines:
                continue
            # First table line must be a header (non-separator data row)
            assert not _is_separator_row(table_lines[0]), (
                f"Chunk {i} starts with separator (no header): {chunk[:120]!r}"
            )
            # Second table line (if present) must be a separator
            if len(table_lines) >= 2:
                assert _is_separator_row(table_lines[1]), (
                    f"Chunk {i} second table line is not separator: {chunk[:120]!r}"
                )

    def test_small_table_unchanged(self):
        """A small table that fits in one chunk must not be modified."""
        table = TABLE_HEADER + "| item1 | ok | note1 |\n"
        chunks = chunk_message("Intro.\n\n" + table)
        assert len(chunks) == 1
        assert table in chunks[0]

    def test_multiple_tables_independent_headers(self):
        """Each table's continuation gets the right header, not another table's."""
        table_a = "| Alpha | Beta |\n|-------|------|\n" + "| a | b |\n" * 40
        table_b = "| Gamma | Delta |\n|-------|-------|\n" + "| c | d |\n" * 40
        text = table_a + "\nSome text between.\n\n" + table_b
        chunks = chunk_message(text, max_chars=600)

        for i, chunk in enumerate(chunks):
            table_lines = [ln for ln in chunk.splitlines() if _is_table_line(ln)]
            if len(table_lines) < 2:
                continue
            # First table line must be a header
            assert not _is_separator_row(table_lines[0]), (
                f"Chunk {i} missing header: {chunk[:120]!r}"
            )
            assert _is_separator_row(table_lines[1]), (
                f"Chunk {i} missing separator: {chunk[:120]!r}"
            )


class TestCloseOpenFence:
    def test_no_fence(self):
        chunk, lang = _close_open_fence("Hello world")
        assert chunk == "Hello world"
        assert lang is None

    def test_balanced_fence(self):
        chunk, lang = _close_open_fence("```python\ncode\n```")
        assert lang is None

    def test_unclosed_fence(self):
        chunk, lang = _close_open_fence("```python\ncode")
        assert chunk.endswith("```")
        assert lang == "python"

    def test_unclosed_fence_no_lang(self):
        chunk, lang = _close_open_fence("```\ncode")
        assert chunk.endswith("```")
        assert lang == ""

    def test_multiple_fences_last_unclosed(self):
        text = "```\nfirst\n```\ntext\n```js\nsecond"
        chunk, lang = _close_open_fence(text)
        assert chunk.endswith("```")
        assert lang == "js"

    def test_multiple_fences_all_closed(self):
        text = "```\nfirst\n```\n```\nsecond\n```"
        chunk, lang = _close_open_fence(text)
        assert lang is None
