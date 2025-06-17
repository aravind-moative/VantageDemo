from pydantic import BaseModel
from typing import List, Dict, Any, Literal

class UserQuery(BaseModel):
    question: str

class ChatResponse(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "MATCH (d:DosageCohort) RETURN d",
                "results": [{
                    "insights": "Based on the data, there are 5 dosage cohorts...",
                    "type": "insight"
                }]
            }
        } 