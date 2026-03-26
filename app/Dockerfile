FROM python:3.12-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/app.py ./
COPY app/api.py ./
COPY app/auth.py ./
COPY app/credits.py ./
COPY app/lemonsqueezy.py ./
COPY app/analysis_queue.py ./
COPY app/projects.py ./
COPY app/views.py ./
COPY app/init.sql ./
COPY app/templates ./templates
COPY app/static ./static

COPY db.py ./db.py
COPY config.py ./config.py

EXPOSE 3000

CMD ["python", "app.py"]
