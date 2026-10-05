# JusticeFlow API

The FastAPI service owns JusticeFlow domain rules, local-model orchestration, persistence, evaluation, and observability.

## Commands

```sh
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --cov=app --cov-report=term-missing
uv run python -m evals.run
uv run alembic upgrade head --sql
```

Runtime configuration uses environment variables prefixed with `JUSTICEFLOW_`. See the repository `.env.example` for the supported deployment values.
