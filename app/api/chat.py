from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.models.chat import UserQuery, ChatResponse
from app.services.gemini_service import gemini_service, GeminiService
from app.db.neo4j_client import neo4j_client, Neo4jClient
from typing import Dict, List, Optional

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Define schema hint for LLM
def get_schema_hint() -> str:
    return """
(:AntibodyDrugConjugate)-[:HAS_DOSAGE_COHORT]->(:DosageCohort)
(:DosageCohort)-[:HAS_AUC]->(:PK_Observation)
(:DosageCohort)-[:HAS_CL]->(:PK_Observation)
(:DosageCohort)-[:HAS_CMAX]->(:PK_Observation)
(:DosageCohort)-[:HAS_TMAX]->(:PK_Observation)
(:DosageCohort)-[:HAS_THALF]->(:PK_Observation)
(:DosageCohort)-[:HAS_AUCLAST]->(:PK_Observation)
(:DosageCohort)-[:HAS_GRADE]->(:GradeValue)
(:DosageCohort)-[:EXPERIENCED_ADVERSE_EVENT]->(:AETermMention)
(:AETermMention)-[:GeneralAEMentioned]->(:AdverseEventTerm)
(:AntibodyDrugConjugate)-[:USES_PAYLOAD_AGENT]->(:PayloadAgent)
(:AntibodyDrugConjugate)-[:HAS_PAYLOAD_CLASS]->(:PayloadClass)
(:AntibodyDrugConjugate)-[:HAS_LINKER_TYPE]->(:LinkerType)
(:AntibodyDrugConjugate)-[:HAS_TARGET]->(:TargetAntigen)
(:Study)-[:INCLUDES_DOSAGE_COHORT]->(:DosageCohort)
(:Study)-[:INVESTIGATES_ADC]->(:AntibodyDrugConjugate)
"""

@router.get("/", response_class=HTMLResponse)
async def get_chat_interface(request: Request):
    try:
        query = """
        MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort:DosageCohort)
        OPTIONAL MATCH (cohort)-->(pk:PK_Observation)
        OPTIONAL MATCH (cohort)-[ae_rel:HAS_AE]->(ae:AdverseEventTerm)
        WITH adc, cohort,
             collect(DISTINCT {
                 parameter: pk.parameter_name,
                 analyte: pk.analyte_component,
                 value: pk.value,
                 unit: pk.unit
             }) AS pk_data,
             collect(DISTINCT {
                 event: ae.name,
                 grade: ae_rel.grade,
                 count: ae_rel.patientCount,
                 percent: ae_rel.patientPercentage,
                 related: ae_rel.drugRelated
             }) AS ae_data
        WITH adc, cohort, pk_data, ae_data,
             [item IN pk_data WHERE item.parameter = 'AUCinf' AND item.analyte = 'ADC'] AS aucinf_adc,
             [item IN pk_data WHERE item.parameter = 'AUCinf' AND item.analyte = 'Free Payload'] AS aucinf_payload,
             [item IN pk_data WHERE item.parameter = 'AUCinf' AND item.analyte = 'Total AB'] AS aucinf_totalab,
             [item IN pk_data WHERE item.parameter = 'AUClast' AND item.analyte = 'ADC'] AS auclast_adc,
             [item IN pk_data WHERE item.parameter = 'AUClast' AND item.analyte = 'Free Payload'] AS auclast_payload,
             [item IN pk_data WHERE item.parameter = 'AUClast' AND item.analyte = 'Total AB'] AS auclast_totalab
        RETURN
            adc.name AS ADC_Name,
            cohort.name AS Dosage,
            [item IN pk_data WHERE item.parameter IS NOT NULL] AS PK_Parameters,
            [item IN ae_data WHERE item.event IS NOT NULL] AS Adverse_Events,
            CASE WHEN size(aucinf_adc) > 0 THEN aucinf_adc[0] ELSE {value: '', unit: ''} END AS AUCinf_ADC,
            CASE WHEN size(aucinf_payload) > 0 THEN aucinf_payload[0] ELSE {value: '', unit: ''} END AS AUCinf_Payload,
            CASE WHEN size(aucinf_totalab) > 0 THEN aucinf_totalab[0] ELSE {value: '', unit: ''} END AS AUCinf_TotalAb,
            CASE WHEN size(auclast_adc) > 0 THEN auclast_adc[0] ELSE {value: '', unit: ''} END AS AUClast_ADC,
            CASE WHEN size(auclast_payload) > 0 THEN auclast_payload[0] ELSE {value: '', unit: ''} END AS AUClast_Payload,
            CASE WHEN size(auclast_totalab) > 0 THEN auclast_totalab[0] ELSE {value: '', unit: ''} END AS AUClast_TotalAb
        ORDER BY ADC_Name, Dosage
        """
        results = await neo4j_client.run_query(query)
        
        # Process results for template
        processed_data = []
        for record in results:
            entry = {
                'ADC_Name': record['ADC_Name'],
                'Dosage': record['Dosage'],
                'PK_Parameters': {},
                'Adverse_Events': record['Adverse_Events']
            }
            for pk in record['PK_Parameters']:
                if pk['parameter'] and pk['analyte'] and pk['value'] != 'NOT FOUND':
                    key = f"{pk['parameter']}_{pk['analyte']}"
                    entry['PK_Parameters'][key] = {
                        'value': pk['value'],
                        'unit': pk['unit']
                    }
            processed_data.append(entry)
        
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "data": processed_data
            }
        )
    except Exception as e:
        print(f"Error loading data: {str(e)}")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "data": []
            }
        )

@router.post("/ask", response_model=ChatResponse)
async def ask_chatbot(query: UserQuery):
    try:
        # Generate Cypher query using LLM
        schema_hint = get_schema_hint()
        cypher_query = await gemini_service.generate_cypher(query.question, schema_hint)
        
        # Clean the Cypher query by removing markdown formatting if present
        if cypher_query.startswith("```"):
            lines = cypher_query.splitlines()
            if len(lines) > 2:
                cypher_query = "\n".join(lines[1:-1])
            else:
                cypher_query = ""
        
        print("\n=== Generated Cypher Query ===")
        print(cypher_query)
        print("=============================\n")
        
        # Execute the query
        results = await neo4j_client.run_query(cypher_query)
        
        # Convert Neo4j results to Python types
        formatted_results = []
        for record in results:
            record_dict = {}
            for key, value in record.items():
                if hasattr(value, 'to_dict'):
                    record_dict[key] = value.to_dict()
                else:
                    record_dict[key] = value
            formatted_results.append(record_dict)
        
        if not formatted_results:
            return ChatResponse(
                query=cypher_query,
                results=[{
                    "message": "I couldn't find any data matching your query. Please try rephrasing your question.",
                    "type": "error"
                }]
            )
        
        # Generate conversational response using LLM
        prompt = f"""
You are a friendly and knowledgeable medical research assistant. Based on the following data from a Neo4j database, provide a clear and conversational response to the user's question.

User Question: "{query.question}"

Data: {formatted_results}

Schema: {schema_hint}

Please provide a response that:
1. Uses a warm, conversational tone as if you're explaining to a colleague
2. Avoids technical jargon unless necessary, and explains any technical terms used
3. Structures the information in a natural flow, like you're telling a story
4. Uses simple, clear language that anyone can understand
5. Includes relevant context to help understand the significance of the findings
6. Suggests a relevant example query or follow-up question to encourage further discussion
7. If the query resembles a predefined query, consider using its structure but generate a fresh response
8. Handles any query parameters or specific terms mentioned in the user's question appropriately

Format the response in a natural, conversational way that feels like a friendly discussion.
"""
        response = await gemini_service.generate_response(prompt, formatted_results)
        
        return ChatResponse(
            query=cypher_query,
            results=[{
                "insights": response,
                "type": "insights"
            }]
        )
    except Exception as e:
        error_message = str(e)
        print(f"\n=== Error ===")
        print(error_message)
        print("=============\n")
        
        return ChatResponse(
            query="Error occurred",
            results=[{
                "message": "An error occurred while processing your request. Please try again.",
                "type": "error"
            }]
        )