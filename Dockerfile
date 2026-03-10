# Build Stage
FROM python:3.11-slim as builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY arkashri ./arkashri

# We'll install to a virtualenv for isolation so we can easily copy it to the final stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies including the package itself
RUN pip install --upgrade pip && \
    pip install --no-cache-dir .

# Production Stage
FROM python:3.11-slim as runner

# Create a non-root user
RUN groupadd -r arkashri && useradd -r -g arkashri -s /sbin/nologin -c "Arkashri Application User" arkashri

WORKDIR /app

# Copy the venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"

# Copy application code
COPY ./arkashri ./arkashri
COPY ./alembic  ./alembic
COPY ./scripts  ./scripts
COPY ./alembic.ini .

# Set strict permissions
RUN chown -R arkashri:arkashri /app

# Switch to non-root user
USER arkashri

# Expose API port
EXPOSE 8080

# Default command can be overridden by Kubernetes for the Worker pod
CMD ["gunicorn", "arkashri.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080"]
