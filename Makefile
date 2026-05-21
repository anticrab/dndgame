.PHONY: help install lint format type test test-cov run clean

PY ?= python

help:
	@echo "Команды:"
	@echo "  make install   — поставить пакет в editable + dev-зависимости"
	@echo "  make lint      — ruff check"
	@echo "  make format    — ruff format"
	@echo "  make type      — mypy"
	@echo "  make test      — pytest"
	@echo "  make test-cov  — pytest с покрытием"
	@echo "  make run       — запустить dnd"
	@echo "  make clean     — удалить кеши"

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check src tests

format:
	$(PY) -m ruff format src tests

type:
	$(PY) -m mypy src

test:
	$(PY) -m pytest

test-cov:
	$(PY) -m pytest --cov --cov-report=term-missing

run:
	$(PY) -m dnd.interfaces.cli.app

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
