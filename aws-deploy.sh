#!/bin/bash

# Update system packages
sudo yum update -y

# Install Docker
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Create app directory
mkdir -p ~/app
cd ~/app

# Create docker-compose.yml
cat > docker-compose.yml << 'EOL'
services:
  neo4j:
    image: neo4j:1.6.1
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    environment:
      - NEO4J_AUTH=neo4j/vantagevantage
      - NEO4J_dbms_memory_pagecache_size=512M
      - NEO4J_dbms_memory_heap_initial__size=512M
      - NEO4J_dbms_memory_heap_max__size=512M
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    networks:
      - app-network

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=vantagevantage
    depends_on:
      - neo4j
    networks:
      - app-network

volumes:
  neo4j_data:
  neo4j_logs:

networks:
  app-network:
    driver: bridge
EOL

# Create Dockerfile
cat > Dockerfile << 'EOL'
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOL

# Create requirements.txt
cat > requirements.txt << 'EOL'
fastapi==0.104.1
uvicorn==0.24.0
python-multipart==0.0.6
jinja2==3.1.2
neo4j==1.6.1
matplotlib==3.8.2
numpy==1.26.2
python-dotenv==1.0.0
EOL

# Start the application
docker-compose up -d 