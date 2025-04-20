FROM python:3.9-slim

WORKDIR /app

# Install minimal dependencies
COPY simplified-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the simplified API file
COPY simplified-api/api.py .

# Create necessary directories for compatibility
RUN mkdir -p /app/api
RUN mkdir -p /app/config
RUN mkdir -p /app/data
RUN mkdir -p /app/models

# Copy our simplified API to the expected location
RUN echo "from api import create_api_app" > /app/api/controller.py

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint
CMD ["uvicorn", "api.controller:create_api_app", "--host", "0.0.0.0", "--port", "8000"]
