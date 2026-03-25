FROM python:3.12-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY api.py ./
COPY auth.py ./
COPY config.py ./
COPY credits.py ./
COPY db.py ./
COPY lemonsqueezy.py ./
COPY projects.py ./
COPY views.py ./
COPY init.sql ./
COPY templates ./templates
COPY static ./static

EXPOSE 3000

CMD ["python", "app.py"]
