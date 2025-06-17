# Create .env file
$envContent = @"
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GEMINI_API_KEY=your_gemini_api_key
"@
$envContent | Out-File -FilePath .env -Encoding UTF8

# Create docker-compose.yml
$dockerComposeContent = @"
services:
  neo4j:
    image: neo4j:3.5.0
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    environment:
      - NEO4J_AUTH=\${NEO4J_USER}/\${NEO4J_PASSWORD}
      - NEO4J_dbms_memory_pagecache_size=512M
      - NEO4J_dbms_memory_heap_initial__size=512M
      - NEO4J_dbms_memory_heap_max__size=512M
      - NEO4J_dbms_security_procedures_unrestricted=apoc.*
      - NEO4J_dbms_security_procedures_allowlist=apoc.*
    volumes:
      - ./neo4j-data/data:/data
      - ./neo4j-data/logs:/logs
      - ./neo4j-dump:/dumps
    networks:
      - app-network
    env_file:
      - .env

  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - NEO4J_URI=\${NEO4J_URI}
      - NEO4J_USER=\${NEO4J_USER}
      - NEO4J_PASSWORD=\${NEO4J_PASSWORD}
      - GEMINI_API_KEY=\${GEMINI_API_KEY}
    depends_on:
      - neo4j
    networks:
      - app-network
    env_file:
      - .env

networks:
  app-network:
    driver: bridge
"@
$dockerComposeContent | Out-File -FilePath docker-compose.yml -Encoding UTF8

# Create Dockerfile
$dockerfileContent = @"
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV NEO4J_URI="bolt://neo4j:7687"
ENV NEO4J_USER="neo4j"
ENV NEO4J_PASSWORD="your_password"
ENV GEMINI_API_KEY="your_gemini_api_key"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
"@
$dockerfileContent | Out-File -FilePath Dockerfile -Encoding UTF8

# Create requirements.txt
$requirementsContent = @"
fastapi==0.68.1
uvicorn==0.15.0
python-multipart==0.0.5
neo4j==4.4.11
pandas==1.3.3
plotly==5.3.1
python-dotenv==0.19.0
google-generativeai==0.3.2
"@
$requirementsContent | Out-File -FilePath requirements.txt -Encoding UTF8

# Create deployment script
$deployScriptContent = @"
#!/bin/bash

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker if not installed
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
fi

# Install Docker Compose if not installed
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.5.0/docker-compose-\$(uname -s)-\$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create necessary directories
mkdir -p neo4j-data/data
mkdir -p neo4j-data/logs
mkdir -p neo4j-dump

# Set permissions
sudo chown -R 7474:7474 neo4j-data

# Build and start containers
sudo docker-compose up --build -d

# Wait for Neo4j to be ready
echo "Waiting for Neo4j to be ready..."
sleep 30

# Import data if dump file exists
if [ -f "neo4j-dump/neo4j.dump" ]; then
    echo "Importing data from dump file..."
    sudo docker-compose exec neo4j neo4j-admin load --from=/dumps/neo4j.dump --database=neo4j --force
    sudo docker-compose restart neo4j
fi

echo "Deployment completed!"
"@
$deployScriptContent | Out-File -FilePath deploy.sh -Encoding UTF8

Write-Host "Files created successfully!"
Write-Host "Please update the .env file with your actual credentials before deploying." 