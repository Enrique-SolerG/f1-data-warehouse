FROM apache/airflow:3.3.1

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .
