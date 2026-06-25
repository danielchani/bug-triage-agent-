FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "bug_triage.main"]
CMD ["--help"]
