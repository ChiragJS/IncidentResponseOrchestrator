FROM python:3.9-slim
WORKDIR /app

# Install kubectl for in-cluster diagnostics
RUN apt-get update && apt-get install -y curl && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && mv kubectl /usr/local/bin/ && \
    apt-get remove -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

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
