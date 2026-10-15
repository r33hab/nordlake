"""Nightly pipeline: ingest every source into bronze, then rebuild the dbt models.

Runs the same CLI a person runs by hand, so the DAG stays a thin schedule and the
logic lives in one place. `NORDLAKE_HOME` is the repo checkout inside the container.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG

try:  # Airflow 3
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:  # Airflow 2
    from airflow.operators.bash import BashOperator

HOME = os.environ.get("NORDLAKE_HOME", "/opt/nordlake")
DATA_DIR = os.environ.get("NORDLAKE_DATA_DIR", f"{HOME}/data")
CLAUDE_PROJECTS = os.environ.get("NORDLAKE_CLAUDE_PROJECTS_DIR")

ENV = {
    "NORDLAKE_DATA_DIR": DATA_DIR,
    "NORDLAKE_DUCKDB": f"{DATA_DIR}/nordlake.duckdb",
}

claude_args = f" --projects-dir {CLAUDE_PROJECTS}" if CLAUDE_PROJECTS else ""

with DAG(
    dag_id="nordlake_daily",
    description="Ingest Nav job ads and Claude Code usage, then run dbt build.",
    schedule="@daily",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=10)},
    tags=["nordlake", "lakehouse"],
) as dag:
    ingest_nav_jobs = BashOperator(
        task_id="ingest_nav_jobs",
        bash_command=f"cd {HOME} && nordlake ingest nav_jobs",
        env=ENV,
        append_env=True,
    )

    ingest_claude_transcripts = BashOperator(
        task_id="ingest_claude_transcripts",
        bash_command=f"cd {HOME} && nordlake ingest claude_transcripts{claude_args}",
        env=ENV,
        append_env=True,
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {HOME}/dbt && dbt build --profiles-dir . "
            f"--vars '{{\"bronze_dir\": \"{DATA_DIR}/bronze\"}}'"
        ),
        env=ENV,
        append_env=True,
    )

    [ingest_nav_jobs, ingest_claude_transcripts] >> dbt_build
