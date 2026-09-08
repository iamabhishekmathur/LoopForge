FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY loopforge /app/loopforge
COPY schemas /app/schemas

RUN pip install --no-cache-dir .

ENTRYPOINT ["loopforge"]
