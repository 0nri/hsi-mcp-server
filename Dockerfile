FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./

RUN pip install --upgrade pip && \
    pip install .

COPY src/ ./src/
COPY .env.example ./

EXPOSE 8080

CMD ["python", "-m", "src.hsi_server.main"]
