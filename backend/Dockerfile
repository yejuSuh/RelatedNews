FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir pipenv

COPY backend/ ./backend/

WORKDIR /app/backend
RUN pipenv install --deploy --system

WORKDIR /app

EXPOSE 8080
ENV PORT=8080

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
