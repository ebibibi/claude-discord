# claude-discord

A Discord frontend for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI. Chat with Claude Code through Discord threads, see real-time status updates, and manage sessions from your phone.

## Features

- **Thread-based conversations** - Each task gets its own Discord thread, mapped to a Claude Code session
- **Real-time status** - Emoji reactions show what Claude is doing (thinking, reading files, editing, running commands)
- **Session persistence** - Continue conversations across messages using Claude Code's built-in session management
- **Fence-aware splitting** - Long responses are split at natural boundaries, never breaking code blocks
- **Concurrent sessions** - Run multiple Claude Code sessions in parallel (configurable limit)

## How It Works

```
You (Discord)  →  claude-discord  →  Claude Code CLI
    ↑                                      ↓
    ←──────── stream-json output ──────────←
```

1. Send a message in the configured Discord channel
2. The bot creates a thread and starts a Claude Code session
3. Stream-json output is parsed in real-time for status updates
4. Claude's response is posted back to the thread
5. Reply in the thread to continue the conversation

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- A Discord bot token with Message Content intent enabled

## Quick Start

```bash
git clone https://github.com/ebibibi/claude-discord.git
cd claude-discord

cp .env.example .env
# Edit .env with your bot token and channel ID

uv run python -m src.main
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_BOT_TOKEN` | Your Discord bot token | (required) |
| `DISCORD_CHANNEL_ID` | Channel ID for Claude chat | (required) |
| `CLAUDE_COMMAND` | Path to Claude Code CLI | `claude` |
| `CLAUDE_MODEL` | Default model | `sonnet` |
| `CLAUDE_PERMISSION_MODE` | Permission mode for CLI | `acceptEdits` |
| `CLAUDE_WORKING_DIR` | Working directory for Claude | current dir |
| `MAX_CONCURRENT_SESSIONS` | Max parallel sessions | `3` |
| `SESSION_TIMEOUT_SECONDS` | Session timeout | `300` |

## Discord Bot Setup

1. Create a new application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a bot and copy the token
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Invite the bot to your server with these permissions:
   - Send Messages
   - Create Public Threads
   - Send Messages in Threads
   - Add Reactions
   - Manage Messages (for reaction cleanup)
   - Read Message History

## Architecture

This project is a **framework** (reusable library) — not a ready-made bot for a specific server.

- **No custom AI logic** - Claude Code handles all reasoning, tool use, and context management
- **No memory system** - Claude Code's built-in session management + CLAUDE.md handle memory
- **No tool definitions** - Claude Code has its own comprehensive tool set

The framework's job is purely UI: accept messages, show status, deliver responses.

### Usage Patterns

**Standalone** — Run `claude-discord` as its own bot process with a dedicated bot token:

```bash
uv run python -m src.main
```

**Cog integration** — Import the `ClaudeChatCog` into your existing discord.py bot. This is the recommended approach if you already have a bot running, since Discord allows only one Gateway connection per token:

```python
from claude_discord.cogs.claude_chat import ClaudeChatCog
from claude_discord.claude.runner import ClaudeRunner
from claude_discord.database.repository import SessionRepository

# In your existing bot setup:
runner = ClaudeRunner(command="claude", model="sonnet")
repo = SessionRepository("data/sessions.db")
await bot.add_cog(ClaudeChatCog(bot, repo, runner))
```

## Inspired By

- [OpenClaw](https://github.com/openclaw/openclaw) - Emoji status reactions, message debouncing, fence-aware chunking
- [claude-code-discord-bot](https://github.com/timoconnellaus/claude-code-discord-bot) - CLI spawn + stream-json approach
- [claude-code-discord](https://github.com/zebbern/claude-code-discord) - Permission control patterns
- [claude-sandbox-bot](https://github.com/RhysSullivan/claude-sandbox-bot) - Thread-per-conversation model

## License

MIT
