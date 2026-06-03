FROM python:3.12-slim

WORKDIR /app

# Install system deps for pymupdf and psycopg2, plus fonts for OG card rendering.
# fonts-noto-cjk / fonts-noto-core guarantee CJK + broad Unicode glyphs are
# present locally so the headless-Chrome OG render never falls back to tofu
# boxes when the Google Fonts fetch is slow or blocked; fonts-dejavu covers the
# Latin serif/sans fallbacks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev gcc libpq-dev \
    fonts-noto-cjk fonts-noto-core fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Playwright + Chromium for OG card rendering on /og/c/{slug}.png. Pulls
# ~170MB of browser + system libs; the share feature shows a tiny grey
# Twitter card without it.
RUN playwright install --with-deps chromium

COPY . .

ENV HOST=0.0.0.0
ENV PORT=8420

EXPOSE 8420

CMD ["sh", "-c", "python -m uvicorn noosphere.api.main:app --host 0.0.0.0 --port ${PORT:-8420} --proxy-headers --forwarded-allow-ips='*'"]
