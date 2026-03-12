# ── Build stage ───────────────────────────────────────────────────────────
FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Render assigns PORT at runtime; default fallback = 8080
ENV PORT=8080

# Expose for Render health checks
EXPOSE 8080

CMD ["python", "bot.py"]
