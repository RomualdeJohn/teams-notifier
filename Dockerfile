FROM registry-jpe1.r-local.net/dockerhub/library/python:3.12-slim

ENV TZ=Asia/Tokyo

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
 && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
 && echo $TZ > /etc/timezone \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g 1000 -r appuser && useradd -u 1000 -r -s /usr/sbin/nologin -g appuser appuser

# Set working directory
WORKDIR /usr/src/sagt-teams-notification

# Copy and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --progress-bar off -r requirements.txt

# Copy application code
COPY . .

# Create logs directory and set permissions for non-root user
RUN mkdir -p logs \
 && chown -R appuser:appuser /usr/src/sagt-teams-notification

# Use non-root user
USER appuser

# Set environment variables
ENV PYTHONPATH=/usr/src/sagt-teams-notification
ENV PYTHONUNBUFFERED=1

# Default command (can be overridden by Kubernetes command)
CMD ["python", "/usr/src/sagt-teams-notification/main.py"]
