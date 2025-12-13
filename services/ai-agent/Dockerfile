FROM python:3.9-slim
WORKDIR /app

# Copy requirements
COPY services/ai-agent/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# Copy source code. 
# We copy to /app/src to match the structure expected by the code (if needed) 
# OR we copy structure properly.
# Given 'CMD ["python", "-m", "src.main"]', we need 'src' package in /app.
COPY services/ai-agent/src/ ./src/

ENV PYTHONPATH="${PYTHONPATH}:/app:/app/src"
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "src.main"]
