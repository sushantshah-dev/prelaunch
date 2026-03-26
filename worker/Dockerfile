FROM python:3.12-alpine

WORKDIR /worker

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/pipeline.py ./pipeline.py
COPY worker/worker.py ./worker.py
COPY worker/spec.py ./spec.py

COPY db.py /worker/db.py
COPY config.py /worker/config.py

CMD python worker.py ${WORKER_COUNT:-2}
