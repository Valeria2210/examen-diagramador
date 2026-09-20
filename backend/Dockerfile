FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-production.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt
RUN groupadd --gid 10001 uml && useradd --uid 10001 --gid uml --create-home uml
COPY --chown=uml:uml . .
RUN mkdir -p /var/lib/uml/generados /var/lib/uml/cache /app/staticfiles && chown -R uml:uml /var/lib/uml /app/staticfiles
USER uml
EXPOSE 8000
CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
