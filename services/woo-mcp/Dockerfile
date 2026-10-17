# Multi-arch: built for linux/amd64 and linux/arm64 with buildx. See D-020.
# Local k3d loads this with `k3d image import` and never pulls from GHCR.
FROM python:3.13-slim

# Non-root. The chart also sets runAsNonRoot, this is the image-side half.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Dependencies first so a code change does not invalidate the wheel layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY woo_mcp ./woo_mcp

USER 10001

ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# No credentials here. They arrive as env from a Kubernetes Secret at runtime.
CMD ["python", "-m", "woo_mcp.server"]
