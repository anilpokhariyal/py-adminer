FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

WORKDIR /app
COPY . /app
ENV FLASK_APP=main.py
ENV PYTHONPATH=/app

EXPOSE 5000

CMD ["python", "main.py"]
