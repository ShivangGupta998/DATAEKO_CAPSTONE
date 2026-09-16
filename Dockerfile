# Stage 1: Build dependencies in virtualenv
FROM python:3.13-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY . .

# Stage 2: Production minimal runtime
FROM python:3.13-slim AS runner

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . .

EXPOSE 8000
CMD ["flask", "--app", "api/app.py", "run", "--host", "0.0.0.0", "--port", "8000"]
