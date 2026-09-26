# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

F1 telemetry data warehouse: Airflow 3 pipelines pull data from the OpenF1 API and load it into a dedicated Postgres warehouse.

Keep this file short and limited to things that are stable and not obvious from the code. When a change makes something here wrong, update this file in the same PR.

## Commands

Python 3.13, managed with **uv**. Always run tools through `uv run` so versions come from `uv.lock`.

```sh
uv sync                                   # install workspace + dev deps
uv run pytest                             # all tests
uv run pytest path/to/test_file.py::test_name   # single test
uv run pre-commit run --all-files         # ruff check/format + pyright, same as CI
uv run pre-commit install                 # installs pre-commit AND commit-msg hooks
```

pytest runs with `asyncio_mode = "auto"`, so async tests don't need `@pytest.mark.asyncio`.

## Architecture

- **uv workspace**: the root project depends on the workspace member `open-f1-client/`. The client is a separate package so the Airflow image can install it on its own, without the rest of the repo (see `docker/Dockerfile`). Runtime dependencies that DAGs need must go into that package (or the image), not only into the root `pyproject.toml`.
- **Two separate Postgres databases, on purpose**: Airflow's metadata DB and the telemetry warehouse are kept apart so Airflow's internal bookkeeping never shares a failure domain with the warehouse data. Don't merge them or write pipeline data to the Airflow DB.

## Conventions

- **Conventional Commits** are enforced by commitizen, both through the commit-msg hook and in CI. CI checks every commit in the PR *and* the PR title, because PRs are squash-merged and the title becomes the commit on `main`.
- `main` is protected, so all changes go through a PR.
