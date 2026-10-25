FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Unprivileged user; /data (cache + exports) is a volume owned by it
RUN useradd --system --uid 1000 app && mkdir -p /data && chown app /data
USER app
VOLUME /data

EXPOSE 8000
# A single worker: export jobs are kept in this process's memory
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
