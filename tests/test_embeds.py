"""Tests for Discord embed builders."""

from __future__ import annotations

from claude_discord.discord_ui.embeds import thinking_embed


class TestThinkingEmbed:
    def test_description_uses_spoiler_and_code_block(self) -> None:
        """Thinking embed must use spoiler+code block for readability across all Discord themes."""
        embed = thinking_embed("Let me think about this.")
        assert embed.description is not None
        assert embed.description.startswith("||```\n")
        assert embed.description.endswith("\n```||")

    def test_thinking_text_preserved(self) -> None:
        """Original thinking text should appear inside the code block."""
        text = "Step 1: analyze. Step 2: respond."
        embed = thinking_embed(text)
        assert text in embed.description

    def test_long_text_truncated(self) -> None:
        """Text exceeding the limit should be truncated with a notice."""
        long_text = "x" * 5000
        embed = thinking_embed(long_text)
        assert len(embed.description) <= 4096
        assert "(truncated)" in embed.description

    def test_short_text_not_truncated(self) -> None:
        """Short text should not be modified."""
        text = "Brief thought."
        embed = thinking_embed(text)
        assert "(truncated)" not in embed.description
        assert text in embed.description

    def test_title(self) -> None:
        """Embed should have the Thinking title."""
        embed = thinking_embed("x")
        assert embed.title is not None
        assert "Thinking" in embed.title
