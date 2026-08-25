PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff

.PHONY: format lint test regression regression-full json-derivatives benchmark clean-bootstrap ci prepare-ga4-full check

GA4_FULL_SEGMENT_DIR ?= data/inbound/ga4/full_2020q4
GA4_FULL_OUTPUT ?= data/staged/ga4/ga4_ecommerce_events_20201101_20210131.csv
GA4_FULL_MANIFEST ?= data/staged/ga4/ga4_ecommerce_events_20201101_20210131.manifest.json

format:
	$(RUFF) format src tests

lint:
	$(RUFF) format --check src tests
	$(PYTHON) -m py_compile src/*.py
	$(RUFF) check src tests

test: lint
	PYTHONPATH=src $(PYTHON) -m pytest -q

regression:
	PYTHONPATH=src $(PYTHON) src/run_project_regression.py --env-file .env

regression-full:
	PYTHONPATH=src $(PYTHON) src/run_full_ga4_regression.py --env-file .env

json-derivatives:
	@echo "Provide --batch-id and --source-quality-run-id explicitly; this target is a reminder, not an implicit write."

benchmark:
	PYTHONPATH=src $(PYTHON) src/benchmark_project.py --env-file .env

clean-bootstrap:
	bash scripts/verify_clean_docker_bootstrap.sh

ci: test

prepare-ga4-full:
	PYTHONPATH=src $(PYTHON) src/prepare_ga4_segmented_import.py \
		--input-dir $(GA4_FULL_SEGMENT_DIR) \
		--start-date 2020-11-01 --end-date 2021-01-31 \
		--output $(GA4_FULL_OUTPUT) --manifest $(GA4_FULL_MANIFEST)

check: test regression
