FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install NumPy first to ensure correct version
COPY fixed-api/requirements.txt .
RUN pip install --no-cache-dir numpy==1.23.5
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY api/ ./api/
COPY utils/ ./utils/
COPY anomaly_detector/ ./anomaly_detector/
COPY action_recommender/ ./action_recommender/
COPY predictive_engine/ ./predictive_engine/
COPY monitoring/ ./monitoring/

# Create necessary directories
RUN mkdir -p /app/config
RUN mkdir -p /app/data
RUN mkdir -p /app/models

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint
CMD ["uvicorn", "api.controller:create_api_app", "--host", "0.0.0.0", "--port", "8000"]
