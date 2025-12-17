# Use an official Python runtime as a parent image
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR='/var/cache/pypoetry'

# Set work directory
WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy poetry dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies, excluding development ones
RUN poetry install --no-root --only main --no-interaction

# --- Final Stage ---
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH=/app

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/


# Copy the application source code
COPY ./doublehelix ./doublehelix
COPY ./examples ./examples
COPY ./alembic ./alembic
COPY ./alembic.ini ./alembic.ini

# The command to run the application will be specified in the docker-compose.yml
# For example:
# CMD ["uvicorn", "examples.fastapi_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# OR
# CMD ["celery", "-A", "examples.fastapi_app.celery_config", "worker", "--loglevel=info"]
