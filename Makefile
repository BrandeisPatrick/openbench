.PHONY: install test lint clean help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies (uv sync)
	uv sync

test:  ## Run the offline test suite (no Docker / network / keys)
	uv run pytest

lint:  ## Lint with ruff
	uv run ruff check src tests

clean:  ## Remove caches
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
