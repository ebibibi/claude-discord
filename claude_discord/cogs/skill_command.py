"""Skill command Cog.

Provides a /skill slash command with autocomplete that lists all available
Claude Code skills from ~/.claude/skills/ and executes the selected one.

Usage:
    /skill [name: goodmorning]   → runs /goodmorning in Claude Code
    /skill [name: todoist]       → runs /todoist in Claude Code
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from ..claude.runner import ClaudeRunner
from ..claude.types import MessageType
from ..discord_ui.chunker import chunk_message
from ..discord_ui.embeds import error_embed, session_complete_embed, session_start_embed
from ..discord_ui.status import StatusManager

logger = logging.getLogger(__name__)

# YAML frontmatter pattern to extract name/description from SKILL.md
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<body>.*?)\n---", re.DOTALL
)
_FIELD_RE = re.compile(r"^(?P<key>\w[\w-]*):\s*(?P<value>.+)$", re.MULTILINE)


def _parse_skill_meta(skill_dir: Path) -> dict[str, str] | None:
    """Read SKILL.md frontmatter and return {name, description} or None."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return None
        fields = dict(_FIELD_RE.findall(m.group("body")))
        name = fields.get("name", skill_dir.name).strip()
        description = fields.get("description", "").strip()
        return {"name": name, "description": description}
    except OSError:
        logger.warning("Failed to read %s", skill_md)
        return None


def _load_skills(skills_dir: Path) -> list[dict[str, str]]:
    """Scan skills_dir and return sorted list of {name, description}."""
    skills: list[dict[str, str]] = []
    if not skills_dir.is_dir():
        logger.warning("Skills directory not found: %s", skills_dir)
        return skills

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        meta = _parse_skill_meta(entry)
        if meta:
            skills.append(meta)

    logger.info("Loaded %d skills from %s", len(skills), skills_dir)
    return skills


class SkillCommandCog(commands.Cog):
    """Cog that exposes Claude Code skills as a /skill slash command."""

    def __init__(
        self,
        bot: commands.Bot,
        repo,
        runner: ClaudeRunner,
        claude_channel_id: int,
        skills_dir: Path | str | None = None,
        allowed_user_ids: set[int] | None = None,
    ) -> None:
        self.bot = bot
        self.repo = repo
        self.runner = runner
        self.claude_channel_id = claude_channel_id
        self._allowed_user_ids = allowed_user_ids

        # Default to ~/.claude/skills/
        if skills_dir is None:
            skills_dir = Path.home() / ".claude" / "skills"
        self._skills_dir = Path(skills_dir)
        self._skills = _load_skills(self._skills_dir)

    def _is_authorized(self, user_id: int) -> bool:
        if self._allowed_user_ids is None:
            return True
        return user_id in self._allowed_user_ids

    async def _skill_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Return up to 25 matching skill names for autocomplete."""
        current_lower = current.lower()
        matches = [
            s for s in self._skills
            if current_lower in s["name"].lower() or current_lower in s["description"].lower()
        ]
        # Trim description to fit Discord's 100-char limit for Choice name
        choices = []
        for s in matches[:25]:
            label = s["name"]
            if s["description"]:
                # Show "name — short description" in the dropdown
                short_desc = s["description"][:60]
                if len(s["description"]) > 60:
                    short_desc += "…"
                label = f"{s['name']} — {short_desc}"
            choices.append(app_commands.Choice(name=label[:100], value=s["name"]))
        return choices

    @app_commands.command(name="skill", description="Claude Codeスキルを実行する")
    @app_commands.describe(name="実行するスキル名（入力で絞り込み）")
    @app_commands.autocomplete(name=_skill_name_autocomplete)
    async def run_skill(self, interaction: discord.Interaction, name: str) -> None:
        """Run a Claude Code skill by name."""
        if not self._is_authorized(interaction.user.id):
            await interaction.response.send_message(
                "このコマンドを使う権限がありません。", ephemeral=True
            )
            return

        # Validate skill name — only alphanumeric, hyphens, underscores
        if not re.match(r"^[\w-]+$", name):
            await interaction.response.send_message(
                f"無効なスキル名です: `{name}`", ephemeral=True
            )
            return

        # Find matching skill (allow partial match for direct typing)
        matched = next((s for s in self._skills if s["name"] == name), None)
        if not matched:
            await interaction.response.send_message(
                f"スキル `{name}` が見つかりません。`/skill` でオートコンプリートを使ってください。",
                ephemeral=True,
            )
            return

        # Defer so we can take time creating thread + running Claude
        await interaction.response.defer()

        # Create a thread in the Claude channel for output
        channel = self.bot.get_channel(self.claude_channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Claudeチャンネルが見つかりません。", ephemeral=True)
            return

        thread = await channel.create_thread(
            name=f"/{name}",
            type=discord.ChannelType.public_thread,
        )

        await interaction.followup.send(
            f"🚀 スキル `/{name}` を実行します → {thread.mention}"
        )

        # The prompt is the skill invocation as Claude Code understands it
        prompt = f"/{name}"
        await self._run_claude_in_thread(thread, prompt, session_id=None)

    @app_commands.command(name="skills", description="利用可能なスキル一覧を表示する")
    async def list_skills(self, interaction: discord.Interaction) -> None:
        """Show all available skills."""
        if not self._is_authorized(interaction.user.id):
            await interaction.response.send_message(
                "このコマンドを使う権限がありません。", ephemeral=True
            )
            return

        lines = [f"**Claude Code スキル一覧** ({len(self._skills)}個)\n"]
        for s in self._skills:
            desc = s["description"][:60] + "…" if len(s["description"]) > 60 else s["description"]
            lines.append(f"• `{s['name']}` — {desc}" if desc else f"• `{s['name']}`")

        # Discord message limit is 2000 chars; split if needed
        text = "\n".join(lines)
        for chunk in chunk_message(text):
            if interaction.response.is_done():
                await interaction.followup.send(chunk, ephemeral=True)
            else:
                await interaction.response.send_message(chunk, ephemeral=True)

    async def _run_claude_in_thread(
        self,
        thread: discord.Thread,
        prompt: str,
        session_id: str | None,
    ) -> None:
        """Execute Claude Code CLI and stream results to the thread."""
        # Create a status proxy on the thread itself (no original message, use thread)
        runner = self.runner.clone()

        accumulated_text = ""
        final_session_id = session_id

        try:
            async for event in runner.run(prompt, session_id=session_id):
                if event.message_type == MessageType.SYSTEM and event.session_id:
                    final_session_id = event.session_id
                    await self.repo.save(thread.id, final_session_id)
                    if not session_id:
                        await thread.send(embed=session_start_embed(final_session_id))

                if event.message_type == MessageType.ASSISTANT:
                    if event.text:
                        accumulated_text = event.text

                if event.is_complete:
                    if event.error:
                        await thread.send(embed=error_embed(event.error))
                    else:
                        response_text = event.text or accumulated_text
                        if response_text:
                            for chunk in chunk_message(response_text):
                                await thread.send(chunk)
                        await thread.send(
                            embed=session_complete_embed(event.cost_usd, event.duration_ms)
                        )
                    if event.session_id:
                        await self.repo.save(thread.id, event.session_id)

        except Exception:
            logger.exception("Error running skill /%s in thread %d", prompt, thread.id)
            await thread.send(embed=error_embed("スキル実行中にエラーが発生しました。"))
