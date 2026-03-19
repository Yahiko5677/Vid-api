# v5 - 2026-03-20
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    wget \
    libfreetype6-dev \
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake fonts into image at build time — no runtime download needed
RUN mkdir -p assets/fonts && \
    wget -q -O assets/fonts/DejaVuSans-Bold.ttf \
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf" && \
    wget -q -O assets/fonts/DejaVuSans.ttf \
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf" && \
    echo "Fonts downloaded ✅"

ENV PORT=8080
EXPOSE 8080

CMD ["python", "bot.py"]
