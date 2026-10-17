# Multi-arch, same pattern as the other services. See D-020.
FROM python:3.13-slim
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway ./gateway
USER 10001
ENV PORT=8080 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
# No credentials in the image. DATABASE_URL, ENCRYPTION_KEY and
# BOOTSTRAP_API_KEY all arrive as env from Kubernetes Secrets.
CMD ["python", "-m", "gateway.app"]
