# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
# Prevents Python from writing pyc files to disc (equivalent to python -B)
ENV PYTHONDONTWRITEBYTECODE 1
# Prevents Python from buffering stdout and stderr (equivalent to python -u)
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed by some Python packages
# e.g., for lxml if not using a binary wheel, or other C extensions
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#  && rm -rf /var/lib/apt/lists/*

# Copy the pyproject.toml and hatchling build files (if any specific ones are needed)
COPY pyproject.toml ./

# Install project dependencies
# Using pip directly with pyproject.toml for modern package management
# Ensure pip is up-to-date
RUN pip install --upgrade pip
# Install dependencies. This will also install the project itself if configured.
# We only install runtime dependencies, not 'dev' extras for a lean image.
RUN pip install .

# Copy the rest of the application code into the container
COPY src/ ./src/
COPY .env.example ./.env.example
# Note: .env file itself should not be copied into the image for security.
# Configuration should be passed via environment variables in Cloud Run.

# Expose the port the app runs on (Cloud Run will set this via $PORT)
# Defaulting to 8080 if $PORT is not set, which uvicorn will use.
EXPOSE 8080

# Define the command to run the application
# Cloud Run will set the $PORT environment variable.
# MCP_SERVER_MODE should be set to "http" in the Cloud Run environment.
CMD ["uvicorn", "src.hsi_server.main:app", "--host", "0.0.0.0", "--port", "8080"]
# When deploying to Cloud Run, the $PORT environment variable will be automatically
# picked up by uvicorn if the --port argument is not hardcoded,
# or you can ensure your main.py reads $PORT.
# The current main.py reads PORT env var, so this CMD is fine.
# Uvicorn will listen on the port specified by the --port flag,
# which main.py sets based on the PORT env var.
