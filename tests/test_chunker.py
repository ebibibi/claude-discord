"""Tests for fence-aware message chunker."""

from claude_discord.discord_ui.chunker import _close_open_fence, chunk_message


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

        # First chunk should close the fence
        # and subsequent chunk should reopen it
        for i, chunk in enumerate(chunks):
            fence_count = chunk.count("```")
            # Each chunk should have balanced fences (even count)
            assert fence_count % 2 == 0, f"Chunk {i} has unbalanced fences: {fence_count}"

    def test_no_empty_chunks(self):
        text = "Hello\n\n\n\nWorld"
        chunks = chunk_message(text, max_chars=10)
        assert all(c.strip() for c in chunks)


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
