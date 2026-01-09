# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Change the working directory to `/app`
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy the project into the image
COPY . /app

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Production stage
FROM python:3.12-slim-bookworm

# Copy the application from the builder
WORKDIR /app
COPY --from=builder /app /app

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Create a directory for WebDAV data
RUN mkdir -p /data && chmod 777 /data
VOLUME /data

# Expose the default port
EXPOSE 8080

# Set default environment variables
ENV WEBDAV_HOST=0.0.0.0
ENV WEBDAV_PORT=8080
ENV WEBDAV_DIR=/data

# Run the WebDAV server
CMD ["sh", "-c", "python -m py_webdav.cmd.server --addr $WEBDAV_HOST --port $WEBDAV_PORT $WEBDAV_DIR"]
