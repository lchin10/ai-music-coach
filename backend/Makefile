.PHONY: install dev run lint format clean

PYTHON=python

install:
	$(PYTHON) -m pip install -e .

dev:
	$(PYTHON) -m pip install -e .[dev]

run:
	$(PYTHON) -m uvicorn app.main:app --reload --env-file .env.local

lint:
	ruff .

format:
	black .

clean:
	rm -rf build dist *.egg-info