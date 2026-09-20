# Образ серверной части информационной системы «Управление сервисным центром».
FROM python:3.11-slim

# PYTHONUNBUFFERED — логи сразу попадают в stdout контейнера,
# PYTHONDONTWRITEBYTECODE — не засоряем образ файлами .pyc.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /code

# Системные библиотеки: gcc нужен для сборки колёс, libpq — для psycopg.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Зависимости копируем отдельно — слой кешируется и не пересобирается
# при каждом изменении исходного кода.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app

# Приложение работает не от root (требование безопасности).
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /code
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
