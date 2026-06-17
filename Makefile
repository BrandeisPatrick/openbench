.PHONY: install test lint demo report clean help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies (uv sync)
	uv sync

test:  ## Run the offline test suite (no Docker / network / keys)
	uv run pytest

lint:  ## Lint with ruff
	uv run ruff check src tests

demo:  ## Offline reward-fingerprint report from local run traces (runs/)
	uv run openbench demo
	@echo "→ open report.md"

clean:  ## Remove caches and generated demo output
	rm -rf .pytest_cache .ruff_cache report.md
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
