# Multi-arch, same pattern as woo-mcp. See D-020.
FROM python:3.13-slim
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fx_mcp ./fx_mcp
USER 10001
ENV PORT=8000 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
# No credentials: the rates API is keyless (D-010).
CMD ["python", "-m", "fx_mcp.server"]
