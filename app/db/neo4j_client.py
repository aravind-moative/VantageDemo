from neo4j import GraphDatabase
from app.core.config import settings

class Neo4jClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    def run_query(self, query: str):
        with self.driver.session() as session:
            result = session.run(query)
            return [record.data() for record in result]

neo4j_client = Neo4jClient() 