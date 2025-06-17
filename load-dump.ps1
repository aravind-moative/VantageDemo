# Create necessary directories
New-Item -ItemType Directory -Force -Path "neo4j-data/data"
New-Item -ItemType Directory -Force -Path "neo4j-data/logs"
New-Item -ItemType Directory -Force -Path "neo4j-dump"

# Create .env file
$envContent = @"
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=vantagevantage
GEMINI_API_KEY=your_gemini_api_key
"@
$envContent | Out-File -FilePath .env -Encoding UTF8

# Start containers
Write-Host "Starting containers..."
docker-compose up -d

# Wait for Neo4j to start
Write-Host "Waiting for Neo4j to start..."
Start-Sleep -Seconds 30

# Stop Neo4j before loading dump
Write-Host "Stopping Neo4j..."
docker-compose stop neo4j
Start-Sleep -Seconds 10  # Wait for Neo4j to fully stop

# Load dump file
Write-Host "Loading dump file..."
try {
    # Use docker run to load the dump while Neo4j is stopped
    docker run --rm -v "${PWD}/neo4j-data:/data" -v "${PWD}/neo4j-dump:/dumps" neo4j:3.5.0 neo4j-admin load --from=/dumps/neo4j.dump --database=neo4j --force
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Dump file loaded successfully"
    } else {
        Write-Host "Failed to load dump file. Exit code: $LASTEXITCODE"
        exit 1
    }
} catch {
    Write-Host "Error loading dump file: $_"
    exit 1
}

# Restart Neo4j
Write-Host "Restarting Neo4j to apply changes..."
docker-compose restart neo4j
Start-Sleep -Seconds 30  # Wait for Neo4j to fully restart

Write-Host "Neo4j dump has been loaded. You can access it at http://localhost:7474"
Write-Host "Login credentials:"
Write-Host "Username: neo4j"
Write-Host "Password: vantagevantage" 