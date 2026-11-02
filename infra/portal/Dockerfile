FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart httpx boto3
COPY infra /app/infra
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "infra.portal.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
