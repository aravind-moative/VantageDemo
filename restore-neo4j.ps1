# Stop any running containers
docker-compose down

# Create necessary directories
New-Item -ItemType Directory -Force -Path "neo4j-data/data"
New-Item -ItemType Directory -Force -Path "neo4j-data/logs"

# Copy your Neo4j data
$neo4jDataPath = "C:\Users\aravi\.Neo4jDesktop\relate-data\dbmss\dbms-85aef49f-a96c-4ac3-8a01-e59cb573bf01\data"
Copy-Item -Path "$neo4jDataPath\*" -Destination "neo4j-data/data" -Recurse -Force

# Start the containers
docker-compose up -d

Write-Host "Neo4j data has been restored. You can access it at http://localhost:7474" 