import matplotlib
matplotlib.use('Agg')  # Set the backend to Agg before importing pyplot

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.api import chat
from app.db.neo4j_client import neo4j_client

app = FastAPI(title="ADC Analysis")

# Store for database schema
DB_SCHEMA = {
    "labels": [],
    "relationships": [],
    "properties": {},
    "node_relationships": {}
}

@app.on_event("startup")
async def startup_event():
    """Initialize database schema at startup"""
    try:
        # Get all relationship types with their source and target nodes
        rel_query = """
        MATCH (n)-[r]->(m)
        RETURN DISTINCT 
            type(r) as relationship_type,
            labels(n) as source_labels,
            labels(m) as target_labels
        ORDER BY relationship_type
        """
        rel_result = await neo4j_client.run_query(rel_query)
        
        # Process relationship results
        relationships = set()
        node_relationships = {}
        
        for record in rel_result:
            rel_type = record["relationship_type"]
            source_label = record["source_labels"][0] if record["source_labels"] else None
            target_label = record["target_labels"][0] if record["target_labels"] else None
            
            relationships.add(rel_type)
            
            if source_label not in node_relationships:
                node_relationships[source_label] = []
            
            node_relationships[source_label].append({
                "relationship": rel_type,
                "target": target_label
            })
        
        DB_SCHEMA["relationships"] = sorted(list(relationships))
        DB_SCHEMA["node_relationships"] = node_relationships

        # Get all node labels
        label_query = """
        CALL db.labels()
        YIELD label
        RETURN collect(label) as labels
        """
        label_result = await neo4j_client.run_query(label_query)
        DB_SCHEMA["labels"] = label_result[0]["labels"] if label_result else []

        # Get sample properties for each label
        for label in DB_SCHEMA["labels"]:
            prop_query = f"""
            MATCH (n:{label})
            RETURN keys(n) as props
            LIMIT 1
            """
            prop_result = await neo4j_client.run_query(prop_query)
            if prop_result:
                DB_SCHEMA["properties"][label] = prop_result[0]["props"]

        print("\n=== Database Schema ===")
        print("\nNode Labels and Properties:")
        for label, props in DB_SCHEMA["properties"].items():
            print(f"\n{label}:")
            for prop in props:
                print(f"  - {prop}")

        print("\nRelationships between Nodes:")
        for label, rels in DB_SCHEMA["node_relationships"].items():
            print(f"\n{label} ->")
            for rel in rels:
                print(f"  - {rel['relationship']} -> {rel['target']}")

        print("\nAll Relationship Types:")
        print(DB_SCHEMA["relationships"])
        print("=====================\n")

    except Exception as e:
        print(f"Error initializing database schema: {str(e)}")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(chat.router)

@app.on_event("shutdown")
async def shutdown_event():
    await neo4j_client.close() 