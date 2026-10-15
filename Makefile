UV ?= uv
DATA_DIR ?= $(CURDIR)/data
DEMO_DIR := $(CURDIR)/demo-data

export NORDLAKE_DATA_DIR ?= $(DATA_DIR)

.PHONY: setup lint test ingest ingest-nav ingest-claude dbt build demo query status airflow clean

setup:            ## install dependencies into .venv
	$(UV) sync

lint:
	$(UV) run ruff check src tests

test:
	$(UV) run pytest -q

ingest:           ## pull new records from every source
	$(UV) run nordlake ingest all

ingest-nav:
	$(UV) run nordlake ingest nav_jobs

ingest-claude:
	$(UV) run nordlake ingest claude_transcripts

dbt:              ## seeds + models + tests against $(DATA_DIR)
	cd dbt && NORDLAKE_DUCKDB=$(NORDLAKE_DATA_DIR)/nordlake.duckdb $(UV) run dbt build --profiles-dir . --vars '{"bronze_dir": "$(NORDLAKE_DATA_DIR)/bronze"}'

build: ingest dbt  ## the nightly run, by hand

demo:             ## end-to-end on the recorded fixtures, into demo-data/ (what CI runs)
	rm -rf $(DEMO_DIR)
	NORDLAKE_DATA_DIR=$(DEMO_DIR) $(UV) run nordlake ingest nav_jobs --fixture tests/fixtures/nav
	NORDLAKE_DATA_DIR=$(DEMO_DIR) $(UV) run nordlake ingest claude_transcripts --projects-dir tests/fixtures/claude_projects
	cd dbt && NORDLAKE_DUCKDB=$(DEMO_DIR)/nordlake.duckdb $(UV) run dbt build --profiles-dir . --vars '{"bronze_dir": "$(DEMO_DIR)/bronze"}'
	NORDLAKE_DATA_DIR=$(DEMO_DIR) $(UV) run nordlake query "select skill, sum(ads) as ads from gold.job_skill_mentions group by 1 order by 2 desc"

query:            ## make query SQL="select ..."
	$(UV) run nordlake query "$(SQL)"

status:
	$(UV) run nordlake status

airflow:
	docker compose up

clean:
	rm -rf $(DEMO_DIR) dbt/target dbt/logs logs
