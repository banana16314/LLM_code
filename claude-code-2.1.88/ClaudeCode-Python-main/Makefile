.PHONY: lint format typecheck test test-unit test-integration test-e2e check install

install:
	pip install -e ".[all]"

lint:
	ruff check cc/ tests/

format:
	ruff format cc/ tests/

typecheck:
	mypy cc/

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-e2e:
	pytest tests/e2e/ -v -m e2e

check: lint typecheck test-unit
