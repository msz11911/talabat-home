FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ /app/server/
COPY web/ /app/web/

WORKDIR /app/server
EXPOSE 8000

CMD exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
