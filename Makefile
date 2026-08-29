.PHONY: setup dev-api dev-web test build check

setup:
	python3 -m venv backend/.venv
	backend/.venv/bin/python -m pip install -e 'backend[dev]'
	npm --prefix frontend install

dev-api:
	cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

dev-web:
	npm --prefix frontend run dev

test:
	cd backend && .venv/bin/python -m pytest -q
	npm --prefix frontend test

build:
	npm --prefix frontend run build

check: test build
