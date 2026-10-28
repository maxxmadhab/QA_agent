# Dockerfile for QA Agent AI-Powered DevOps QA Platform
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Newman CLI globally for Postman collection execution
RUN npm install -g newman

# Copy dependency files
COPY pyproject.toml README.md LICENSE ./
COPY qa_agent ./qa_agent

# Install Python package and optional dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -e ".[all,dev]" && \
    pip install --no-cache-dir locust

# Ensure Playwright browsers are installed
RUN playwright install chromium

# Entrypoint
ENTRYPOINT ["qa-agent"]
CMD ["--help"]
