FROM node:20-slim AS node-base

RUN npm install -g editly


FROM python:3.11-slim AS runtime

COPY --from=node-base /usr/local/bin/node /usr/local/bin/node
COPY --from=node-base /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/.bin/editly /usr/local/bin/editly \
    && ln -s /usr/local/bin/node /usr/local/bin/nodejs

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-inter \
    fonts-noto \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash vidapi
WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e "." 2>/dev/null || pip install --no-cache-dir .

COPY . .
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/data && chown -R vidapi:vidapi /app/data

USER vidapi

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
