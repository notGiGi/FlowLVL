FROM python:3.9-slim

WORKDIR /app

# Install minimal dependencies
COPY minimal-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the minimal API file
COPY minimal-api/app.py .

# Expose port
EXPOSE 8080

# Start app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
