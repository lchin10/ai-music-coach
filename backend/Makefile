.PHONY: install dev run test lint format clean

PYTHON=python

install:
	$(PYTHON) -m pip install -e .

dev:
	$(PYTHON) -m pip install -e .[dev]

run:
	$(PYTHON) -m uvicorn app.main:app --reload --env-file .env.local

test:
	$(PYTHON) -m pytest -q

lint:
	ruff .

format:
	black .

clean:
	rm -rf build dist *.egg-info