FROM python:3.9-slim
WORKDIR /app

# Copiar e instalar dependencias
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código y carpetas necesarias
COPY api/ ./api/
COPY utils/ ./utils/
COPY anomaly_detector/ ./anomaly_detector/
COPY action_recommender/ ./action_recommender/
COPY predictive_engine/ ./predictive_engine/
COPY monitoring/ ./monitoring/

EXPOSE 8000
CMD ["uvicorn", "api.controller:create_api_app", "--host", "0.0.0.0", "--port", "8000"]
