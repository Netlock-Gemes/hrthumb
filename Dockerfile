FROM python:3.12-slim

# tgcrypto builds a C extension from source and needs a compiler + libc
# headers (stdint.h etc.) — build-essential provides gcc plus libc6-dev.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
