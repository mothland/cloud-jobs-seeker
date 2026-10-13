"""Optional: run jobseeker on Prefect Cloud's free managed work pool.

    pip install -r requirements-prefect.txt
    prefect cloud login
    prefect work-pool create jobseeker --type prefect:managed
    python -m jobseeker.prefect_flow deploy

`deploy` copies DATABASE_URL and THEIRSTACK_API_KEYS from your .env into Prefect
Secret blocks, then registers a scheduled deployment that pulls this repo from git
(so it uses the searches.toml you've pushed).
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess

from prefect import flow, get_run_logger
from prefect.blocks.system import Secret

# Secret block name -> environment variable it fills.
SECRETS = {
    "jobseeker-database-url": "DATABASE_URL",
    "jobseeker-theirstack-api-keys": "THEIRSTACK_API_KEYS",
}

PIP_PACKAGES = ["psycopg[binary]>=3.2", "requests>=2.31", "python-dotenv>=1.0"]


def _load_secrets() -> None:
    for block, env in SECRETS.items():
        if not os.getenv(env):
            os.environ[env] = Secret.load(block).get()


class _PrefectHandler(logging.Handler):
    """Forwards jobseeker's log records to the Prefect run logger so they show in the UI."""

    def emit(self, record: logging.LogRecord) -> None:
        from jobseeker import config

        get_run_logger().log(record.levelno, config.redact(record.getMessage()))


@flow(name="jobseeker-ingest", retries=2, retry_delay_seconds=600)
def ingest(search: list[str] | None = None) -> dict:
    from jobseeker import ingest as core

    logger = logging.getLogger("jobseeker")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # the run logger already prints to the console
    if not any(isinstance(h, _PrefectHandler) for h in logger.handlers):
        logger.addHandler(_PrefectHandler())
    _load_secrets()
    return core.run(only=search)


def _repo_url() -> str:
    url = os.getenv("JOBSEEKER_REPO_URL")
    if url:
        return url
    return subprocess.check_output(["git", "remote", "get-url", "origin"], text=True).strip()


def deploy(work_pool: str, cron: str, branch: str) -> None:
    from jobseeker import config

    values = {"DATABASE_URL": config.database_url(), "THEIRSTACK_API_KEYS": ",".join(config.theirstack_api_keys())}
    for block, env in SECRETS.items():
        Secret(value=values[env]).save(block, overwrite=True)
        print(f"✓ Saved {env} to Prefect Secret '{block}'")

    from prefect.runner.storage import GitRepository

    # Private repos need a token Prefect can clone with (GitHub: fine-grained, Contents read-only).
    credentials = None
    token = os.getenv("JOBSEEKER_GIT_TOKEN")
    if token:
        Secret(value=token).save("jobseeker-git-token", overwrite=True)
        credentials = {"access_token": Secret.load("jobseeker-git-token")}
        print("✓ Saved JOBSEEKER_GIT_TOKEN to Prefect Secret 'jobseeker-git-token'")

    repo = _repo_url()
    ingest.from_source(
        source=GitRepository(url=repo, branch=branch, credentials=credentials),
        entrypoint="jobseeker/prefect_flow.py:ingest",
    ).deploy(
        name="jobseeker",
        work_pool_name=work_pool,
        cron=cron,
        job_variables={"pip_packages": PIP_PACKAGES},
    )
    print(config.redact(f"✓ Deployed from {repo} ({branch}) to work pool '{work_pool}' on schedule '{cron}'"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m jobseeker.prefect_flow")
    sub = parser.add_subparsers(dest="command", required=True)
    p_deploy = sub.add_parser("deploy", help="save secrets and register the scheduled deployment")
    p_deploy.add_argument("--work-pool", default="jobseeker")
    p_deploy.add_argument("--cron", default="0 6 * * 1,4", help="UTC cron schedule (default: Mon & Thu 06:00)")
    p_deploy.add_argument("--branch", default="main")
    sub.add_parser("run", help="run the flow once, locally")
    args = parser.parse_args()

    if args.command == "deploy":
        deploy(args.work_pool, args.cron, args.branch)
    else:
        ingest()
