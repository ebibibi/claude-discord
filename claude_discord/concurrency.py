"""Concurrency awareness for multiple simultaneous Claude Code sessions.

Layer 1: Every session receives a generic concurrency warning in its prompt.
Layer 2: An in-memory registry tracks active sessions so each one knows
         what others are doing and can avoid conflicts.

See: https://github.com/ebibibi/claude-code-discord-bridge/issues/52
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Layer 2: Active Session Registry
# ---------------------------------------------------------------------------


@dataclass
class ActiveSession:
    """Tracks a single active Claude Code session."""

    thread_id: int
    description: str
    working_dir: str | None = None


_BASE_CONCURRENCY_NOTICE = """\
[CONCURRENCY NOTICE] You are running via Discord. \
Multiple Claude Code sessions may be active simultaneously. \
To avoid conflicts:

- **Git**: Before making changes, create a branch or worktree \
(`git worktree add ../wt-{thread_id} -b session/{thread_id}`). \
Always commit and push before finishing — uncommitted changes in a shared \
working directory WILL be lost when another session switches branches.
- **Files**: Another session may be editing the same files outside of git. \
Check for recent modifications before overwriting.
- **Ports & processes**: Shared network ports or lock files may already be in use. \
Verify availability before binding.
- **Resources**: Shared databases, APIs with rate limits, or singleton processes \
may be accessed by other sessions concurrently.

If you detect a potential conflict with another session, \
stop and warn the user before proceeding.\
"""

_OTHER_SESSIONS_HEADER = """
Currently active sessions (avoid conflicts with these):
"""


class SessionRegistry:
    """Thread-safe registry of active Claude Code sessions.

    Designed to be shared across all Cogs in a single bot instance.
    """

    def __init__(self) -> None:
        self._sessions: dict[int, ActiveSession] = {}
        self._lock = threading.Lock()

    def register(
        self,
        thread_id: int,
        description: str,
        working_dir: str | None = None,
    ) -> None:
        """Register or replace an active session."""
        with self._lock:
            self._sessions[thread_id] = ActiveSession(
                thread_id=thread_id,
                description=description,
                working_dir=working_dir,
            )

    def unregister(self, thread_id: int) -> None:
        """Remove a session from the registry."""
        with self._lock:
            self._sessions.pop(thread_id, None)

    def update(
        self,
        thread_id: int,
        *,
        description: str | None = None,
        working_dir: str | None = None,
    ) -> None:
        """Update fields of an existing session. No-op if not registered."""
        with self._lock:
            session = self._sessions.get(thread_id)
            if session is None:
                return
            if description is not None:
                session.description = description
            if working_dir is not None:
                session.working_dir = working_dir

    def list_active(self) -> list[ActiveSession]:
        """Return all active sessions."""
        with self._lock:
            return list(self._sessions.values())

    def list_others(self, thread_id: int) -> list[ActiveSession]:
        """Return all active sessions except the given thread."""
        with self._lock:
            return [s for s in self._sessions.values() if s.thread_id != thread_id]

    def build_concurrency_notice(self, thread_id: int) -> str:
        """Build the full concurrency notice for a session.

        Combines the base Layer 1 warning with Layer 2 context about
        other active sessions.
        """
        notice = _BASE_CONCURRENCY_NOTICE.format(thread_id=thread_id)
        others = self.list_others(thread_id)
        if others:
            notice += _OTHER_SESSIONS_HEADER
            for s in others:
                line = f"- {s.description}"
                if s.working_dir:
                    line += f" (working in {s.working_dir})"
                notice += line + "\n"
            notice += "\nIf your work may conflict with any of the above, stop and warn the user.\n"
        return notice
