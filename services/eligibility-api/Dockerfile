FROM python:3.12-slim

ARG RELEASE_VERSION=v1.0.0-good
ARG BROKEN_CANARY=false

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    AEGISOPS_RELEASE_VERSION=${RELEASE_VERSION} \
    AEGISOPS_BROKEN_CANARY=${BROKEN_CANARY}

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared /app/shared
COPY eligibility-api/main.py /app/main.py

EXPOSE 8081
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
