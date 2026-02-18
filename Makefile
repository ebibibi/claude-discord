.PHONY: setup format check test ci

# One-time setup after cloning: register the committed git hooks.
setup:
	git config core.hooksPath .githooks
	@echo "✅ Git hooks configured (.githooks/pre-commit active)"

# Auto-format all Python source files.
format:
	uv run ruff format claude_discord/ tests/

# Lint check (no auto-fix) — same as CI.
check:
	uv run ruff format --check claude_discord/ tests/
	uv run ruff check claude_discord/ tests/

# Run the full test suite.
test:
	uv run pytest tests/

# Full CI simulation: format check + lint + tests.
ci: check test
