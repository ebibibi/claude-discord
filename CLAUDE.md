# claude-discord

Discord frontend for Claude Code CLI.

## Architecture

- **Python 3.11+** with discord.py v2
- **Cog pattern** for modular features
- **Repository pattern** for data access (SQLite via aiosqlite)
- **asyncio.subprocess** for Claude Code CLI invocation

## Key Design Decisions

1. **CLI spawn, not API**: We invoke `claude -p --output-format stream-json` as a subprocess, not the Anthropic API directly. This gives us all Claude Code features (CLAUDE.md, skills, tools, memory) for free.
2. **Thread = Session**: Each Discord thread maps 1:1 to a Claude Code session ID. Replies in a thread continue the same session via `--resume`.
3. **Emoji reactions for status**: Non-intrusive progress indication on the user's message.
4. **Fence-aware chunking**: Never split Discord messages inside a code block.

## Package Management

Uses **uv** for fast dependency management. No venv setup needed.

## Running

```bash
cp .env.example .env
# Edit .env with your Discord bot token and channel ID
uv run python -m src.main
```

## Testing

```bash
uv run pytest tests/ -v --cov=src
```

## Project Structure

- `src/main.py` - Entry point (bot + event loop)
- `src/bot.py` - Discord Bot class
- `src/cogs/claude_chat.py` - Main chat Cog (thread creation, message handling)
- `src/claude/runner.py` - Claude CLI subprocess manager
- `src/claude/parser.py` - stream-json event parser
- `src/claude/types.py` - Type definitions for SDK messages
- `src/database/models.py` - SQLite schema
- `src/database/repository.py` - Session CRUD operations
- `src/discord_ui/status.py` - Emoji reaction status manager
- `src/discord_ui/chunker.py` - Fence-aware message splitting
- `src/discord_ui/embeds.py` - Discord embed builders
