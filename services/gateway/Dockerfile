# Multi-arch, same pattern as the other services. See D-020.
FROM python:3.13-slim
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Vendor React and htm into the image. Pinned versions, fetched once at
# build time, so the dashboard has no CDN dependency at runtime and works
# on a cluster with no internet access.
ADD https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js \
    /app/gateway/static/vendor/react.production.min.js
ADD https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js \
    /app/gateway/static/vendor/react-dom.production.min.js
ADD https://cdnjs.cloudflare.com/ajax/libs/htm/3.1.1/htm.js \
    /app/gateway/static/vendor/htm.js
RUN chmod -R a+r /app/gateway/static

COPY gateway ./gateway
USER 10001
ENV PORT=8080 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
# No credentials in the image. DATABASE_URL, ENCRYPTION_KEY and
# BOOTSTRAP_API_KEY all arrive as env from Kubernetes Secrets.
CMD ["python", "-m", "gateway.app"]
