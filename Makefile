.PHONY: lint format test

lint:
	ruff check .
	black --check .
	mypy .

format:
	black .
	ruff check --fix .

test:
	pytest -q


