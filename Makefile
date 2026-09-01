# Convenience targets. Windows users without `make` can run the commands directly.
.PHONY: install lint format test build clean

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

test:
	python -m pytest

build:
	python -m pip install build twine
	python -m build
	python -m twine check dist/*

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache htmlcov .coverage
