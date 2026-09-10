FROM python:3.13-slim

WORKDIR /app

COPY api/requirements.txt .

RUN pip install --no-cache-dir -r api/requirements.txt

COPY . .

EXPOSE 8000
CMD ["flask", "--app", "api/app.py", "run", "--host", "0.0.0.0", "--port", "8000"]
