FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-vision.txt ./
ARG ENABLE_VISION=false
RUN if [ "$ENABLE_VISION" = "true" ]; then pip install --no-cache-dir -r requirements-vision.txt; else pip install --no-cache-dir -r requirements.txt; fi
COPY server.py https_setup.py vision.py scenarios.json ./
COPY public ./public
COPY models ./models
EXPOSE 8000
CMD ["python", "server.py"]
