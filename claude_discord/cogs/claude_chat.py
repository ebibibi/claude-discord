"""Claude Code chat Cog.

Handles the core message flow:
1. User sends message in the configured channel
2. Bot creates a thread (or continues in existing thread)
3. Claude Code CLI is invoked with stream-json output
4. Status reactions and tool embeds are posted in real-time
5. Final response is posted to the thread
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..claude.runner import ClaudeRunner
from ..claude.types import MessageType, SessionState
from ..database.repository import SessionRepository
from ..discord_ui.chunker import chunk_message
from ..discord_ui.embeds import (
    error_embed,
    session_complete_embed,
    session_start_embed,
    tool_use_embed,
)
from ..discord_ui.status import StatusManager

if TYPE_CHECKING:
    from ..bot import ClaudeDiscordBot

logger = logging.getLogger(__name__)


class ClaudeChatCog(commands.Cog):
    """Cog that handles Claude Code conversations via Discord threads."""

    def __init__(
        self,
        bot: ClaudeDiscordBot,
        repo: SessionRepository,
        runner: ClaudeRunner,
        max_concurrent: int = 3,
    ) -> None:
        self.bot = bot
        self.repo = repo
        self.runner = runner
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_runners: dict[int, ClaudeRunner] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages."""
        # Ignore bot messages
        if message.author.bot:
            return

        # Check if message is in the configured channel (new conversation)
        if message.channel.id == self.bot.channel_id:
            await self._handle_new_conversation(message)
            return

        # Check if message is in a thread under the configured channel
        if isinstance(message.channel, discord.Thread):
            if message.channel.parent_id == self.bot.channel_id:
                await self._handle_thread_reply(message)

    @app_commands.command(name="clear", description="Reset the Claude Code session for this thread")
    async def clear_session(self, interaction: discord.Interaction) -> None:
        """Reset the session for the current thread."""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "This command can only be used in a Claude chat thread.", ephemeral=True
            )
            return

        # Kill active runner if any
        runner = self._active_runners.get(interaction.channel.id)
        if runner:
            await runner.kill()
            del self._active_runners[interaction.channel.id]

        deleted = await self.repo.delete(interaction.channel.id)
        if deleted:
            await interaction.response.send_message(
                "\U0001f504 Session cleared. Next message will start a fresh session."
            )
        else:
            await interaction.response.send_message(
                "No active session found for this thread.", ephemeral=True
            )

    async def _handle_new_conversation(self, message: discord.Message) -> None:
        """Create a new thread and start a Claude Code session."""
        # Create thread from the message
        thread_name = message.content[:100] if message.content else "Claude Chat"
        thread = await message.create_thread(name=thread_name)

        await self._run_claude(message, thread, message.content, session_id=None)

    async def _handle_thread_reply(self, message: discord.Message) -> None:
        """Continue a Claude Code session in an existing thread."""
        thread = message.channel
        assert isinstance(thread, discord.Thread)

        # Look up existing session
        record = await self.repo.get(thread.id)
        session_id = record.session_id if record else None

        await self._run_claude(message, thread, message.content, session_id=session_id)

    async def _run_claude(
        self,
        user_message: discord.Message,
        thread: discord.Thread,
        prompt: str,
        session_id: str | None,
    ) -> None:
        """Execute Claude Code CLI and stream results to the thread."""
        if self._semaphore.locked():
            await thread.send(
                f"\u23f3 Waiting for a free session slot... "
                f"({self._max_concurrent} max sessions running)"
            )

        async with self._semaphore:
            status = StatusManager(user_message)
            await status.set_thinking()

            # Create a fresh runner for this session (clone shares config, not process state)
            runner = self.runner.clone()
            self._active_runners[thread.id] = runner

            state = SessionState(session_id=session_id, thread_id=thread.id)

            try:
                async for event in runner.run(prompt, session_id=session_id):
                    # System message: capture session_id
                    if event.message_type == MessageType.SYSTEM and event.session_id:
                        state.session_id = event.session_id
                        # Save session mapping
                        await self.repo.save(thread.id, state.session_id)
                        if not session_id:
                            # First message - show session start
                            await thread.send(embed=session_start_embed(state.session_id))

                    # Assistant message: text or tool use
                    if event.message_type == MessageType.ASSISTANT:
                        if event.text:
                            state.accumulated_text = event.text

                        if event.tool_use:
                            await status.set_tool(event.tool_use.category)
                            embed = tool_use_embed(event.tool_use, in_progress=True)
                            msg = await thread.send(embed=embed)
                            state.active_tools[event.tool_use.tool_id] = msg

                    # User message (tool result): update tool embed
                    # TODO(Phase 2): edit state.active_tools[event.tool_result_id] embed to "done" state
                    if event.message_type == MessageType.USER and event.tool_result_id:
                        await status.set_thinking()

                    # Result: session complete
                    if event.is_complete:
                        if event.error:
                            await thread.send(embed=error_embed(event.error))
                            await status.set_error()
                        else:
                            # Post the final text response
                            response_text = event.text or state.accumulated_text
                            if response_text:
                                chunks = chunk_message(response_text)
                                for chunk in chunks:
                                    await thread.send(chunk)

                            await thread.send(
                                embed=session_complete_embed(event.cost_usd, event.duration_ms)
                            )
                            await status.set_done()

                        # Update session mapping
                        if event.session_id:
                            await self.repo.save(thread.id, event.session_id)

            except Exception:
                logger.exception("Error running Claude CLI for thread %d", thread.id)
                await thread.send(embed=error_embed("An unexpected error occurred."))
                await status.set_error()
            finally:
                self._active_runners.pop(thread.id, None)


