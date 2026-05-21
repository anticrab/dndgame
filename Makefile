.PHONY: help install install-dev lint format type test test-cov test-unit test-integration test-e2e test-fast test-property check run clean docker-build docker-test pre-commit-install pre-commit

PY ?= python3
PIP ?= $(PY) -m pip
PYTEST ?= $(PY) -m pytest

help:
	@echo "Команды:"
	@echo ""
	@echo "  install        — установить пакет в editable"
	@echo "  install-dev    — установить пакет + dev-инструменты"
	@echo ""
	@echo "  lint           — ruff check"
	@echo "  format         — ruff format"
	@echo "  type           — mypy"
	@echo "  check          — lint + type (без тестов)"
	@echo ""
	@echo "  test           — все тесты"
	@echo "  test-cov       — все тесты с покрытием (fail_under = 85)"
	@echo "  test-unit      — только unit"
	@echo "  test-integration — только integration"
	@echo "  test-e2e       — только e2e"
	@echo "  test-fast      — unit, fail-fast"
	@echo "  test-property  — только property-based (HYPOTHESIS_PROFILE=ci)"
	@echo ""
	@echo "  run            — dnd --help"
	@echo ""
	@echo "  pre-commit-install — установить pre-commit-хуки в .git/hooks"
	@echo "  pre-commit     — прогнать все pre-commit-хуки на всех файлах"
	@echo ""
	@echo "  docker-build   — собрать dev-образ (Dockerfile.dev)"
	@echo "  docker-test    — прогнать полный CI-цикл в Docker"
	@echo ""
	@echo "  clean          — удалить кеши"

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[dev]"

lint:
	$(PY) -m ruff check src tests

format:
	$(PY) -m ruff format src tests

type:
	$(PY) -m mypy src

check: lint type

test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov --cov-report=term-missing --cov-report=html

test-unit:
	$(PYTEST) tests/unit -q

test-integration:
	$(PYTEST) tests/integration -q -m integration

test-e2e:
	$(PYTEST) tests/e2e -q -m e2e

test-fast:
	$(PYTEST) tests/unit -x -q --tb=short

test-property:
	HYPOTHESIS_PROFILE=ci $(PYTEST) -m property -q

run:
	$(PY) -m dnd.interfaces.cli --help

pre-commit-install:
	pre-commit install
	pre-commit install --hook-type pre-push

pre-commit:
	pre-commit run --all-files

docker-build:
	docker build -f Dockerfile.dev -t dnd-dev:latest .

docker-test:
	docker run --rm -v "$(PWD)":/app -w /app dnd-dev:latest \
		bash -lc "ruff check src tests && mypy src && pytest --cov --cov-report=term-missing"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis build dist *.egg-info htmlcov coverage.xml .coverage*
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
