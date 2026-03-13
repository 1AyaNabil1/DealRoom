# Use the official Python slim image for a smaller footprint
FROM python:3.11-slim

# Install system dependencies for PyAudio and general build tools
RUN apt-get update && apt-get install -y \
    gcc \
    portaudio19-dev \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY src/ ./src/
COPY static/ ./static/
COPY scripts/ ./scripts/

# Expose the port (Cloud Run sets PORT automatically)
ENV PORT 8080
EXPOSE 8080

# Command to run the application using uvicorn
CMD ["sh", "-c", "uvicorn src.server:app --host 0.0.0.0 --port $PORT"]
