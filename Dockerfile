FROM python:3.12-slim

WORKDIR /app

# Install system deps for pymupdf and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HOST=0.0.0.0
ENV PORT=8420

EXPOSE 8420

CMD ["python", "-m", "uvicorn", "noosphere.api.main:app", "--host", "0.0.0.0", "--port", "8420"]
