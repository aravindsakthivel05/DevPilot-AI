.PHONY: setup api api-local ui test format format-check lint check runner runner-petclinic runner-commons runner-mockito eval-real eval-dataset load-references validate-local validate-java

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'
	cd frontend && npm install

api:
	.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000

api-local:
	DEVPILOT_LANGGRAPH_ENABLED=1 DEVPILOT_LLM_BASE_URL=http://127.0.0.1:11434/v1 DEVPILOT_LLM_MODEL=llama3.2:latest DEVPILOT_PROPOSAL_MODEL=qwen2.5-coder:7b DEVPILOT_EMBEDDING_MODEL=nomic-embed-text .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000

ui:
	cd frontend && npm run dev

test:
	.venv/bin/python -m pytest -q

format:
	.venv/bin/ruff format backend tests examples scripts
	cd frontend && npm run format

format-check:
	.venv/bin/ruff format --check backend tests examples scripts
	cd frontend && npm run format:check

lint:
	.venv/bin/ruff check backend tests examples scripts

check: test format-check lint

runner:
	docker build -f infra/Dockerfile.runner -t devpilot-runner:local .

runner-petclinic:
	.venv/bin/python -m scripts.build_java_runner petclinic

runner-commons:
	.venv/bin/python -m scripts.build_java_runner commons-lang

runner-mockito:
	.venv/bin/python -m scripts.build_java_runner mockito

eval-real:
	.venv/bin/python -m scripts.evaluate_repositories $(EVAL_REPOS)

eval-dataset:
	.venv/bin/python -m scripts.evaluate_dataset > evaluation/baseline.json

load-references:
	.venv/bin/python -m scripts.load_reference_repositories

validate-local:
	.venv/bin/python -m scripts.validate_local_model
	.venv/bin/python -m scripts.validate_container

validate-java:
	.venv/bin/python -m scripts.validate_java_runners
