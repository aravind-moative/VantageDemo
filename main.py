from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os
import base64
import io
import matplotlib.pyplot as plt
import pandas as pd
from pydantic import BaseModel
import google.generativeai as genai
import matplotlib
import numpy as np
import plotly.express as px
import json
from typing import List, Dict, Any

matplotlib.use('Agg')  # Set the backend to Agg before importing pyplot

load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

class UserQuery(BaseModel):
    question: str

def ask_gemini(prompt: str) -> str:
    response = model.generate_content(prompt)
    return response.text.strip()

CYPHER_QUERY = """
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort:DosageCohort)
OPTIONAL MATCH (cohort)-[:HAS_AUC]->(auc:PK_Observation)
OPTIONAL MATCH (cohort)-[:HAS_AUCLAST]->(auclast:PK_Observation)
OPTIONAL MATCH (cohort)-[:HAS_CMAX]->(cmax:PK_Observation)
OPTIONAL MATCH (cohort)-[:HAS_THALF]->(thalf:PK_Observation)
OPTIONAL MATCH (cohort)-[:HAS_TMAX]->(tmax:PK_Observation)
OPTIONAL MATCH (cohort)-[ae_rel:HAS_AE]->(ae:AdverseEventTerm)

WITH adc, cohort,
     collect(DISTINCT {
         parameter: 'AUC',
         analyte: auc.analyte_component,
         value: auc.value,
         unit: auc.unit
     }) AS auc_data,
     collect(DISTINCT {
         parameter: 'AUCLAST',
         analyte: auclast.analyte_component,
         value: auclast.value,
         unit: auclast.unit
     }) AS auclast_data,
     collect(DISTINCT {
         parameter: 'CMAX',
         analyte: cmax.analyte_component,
         value: cmax.value,
         unit: cmax.unit
     }) AS cmax_data,
     collect(DISTINCT {
         parameter: 'THALF',
         analyte: thalf.analyte_component,
         value: thalf.value,
         unit: thalf.unit
     }) AS thalf_data,
     collect(DISTINCT {
         parameter: 'TMAX',
         analyte: tmax.analyte_component,
         value: tmax.value,
         unit: tmax.unit
     }) AS tmax_data,
     collect(DISTINCT {
         event: ae.name,
         grade: ae_rel.grade,
         count: ae_rel.patientCount,
         percent: ae_rel.patientPercentage,
         related: ae_rel.drugRelated
     }) AS ae_data

RETURN 
  adc.name AS ADC_Name,
    cohort.name AS Dosage,
    [item IN auc_data WHERE item.value IS NOT NULL] AS AUC_Data,
    [item IN auclast_data WHERE item.value IS NOT NULL] AS AUCLAST_Data,
    [item IN cmax_data WHERE item.value IS NOT NULL] AS CMAX_Data,
    [item IN thalf_data WHERE item.value IS NOT NULL] AS THALF_Data,
    [item IN tmax_data WHERE item.value IS NOT NULL] AS TMAX_Data,
    [item IN ae_data WHERE item.event IS NOT NULL] AS Adverse_Events
ORDER BY
    ADC_Name, Dosage
"""

# Unit conversion factors
UNIT_CONVERSIONS = {
    'Cmax': {
        'µg/mL': 1.0,
        'mg/mL': 1000.0,
        'ng/mL': 0.001,
        'g/L': 1.0
    },
    'AUC': {
        'µg*day/mL': 1.0,
        'mg*day/mL': 1000.0,
        'ng*day/mL': 0.001,
        'g*day/L': 1.0
    }
}

def convert_unit(value: float, from_unit: str, to_unit: str, param_type: str) -> float:
    """Convert a value from one unit to another for a given parameter type."""
    if from_unit == to_unit:
        return value
    
    if param_type not in UNIT_CONVERSIONS:
        return value
    
    conversions = UNIT_CONVERSIONS[param_type]
    if from_unit not in conversions or to_unit not in conversions:
        return value
    
    # Convert to base unit first, then to target unit
    base_value = value / conversions[from_unit]
    return base_value * conversions[to_unit]

def get_available_units(param_type: str) -> List[str]:
    """Get list of available units for a parameter type."""
    return list(UNIT_CONVERSIONS.get(param_type, {}).keys())

def plot_to_base64(fig):
    """Convert a matplotlib figure to a base64-encoded string"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return img_str

@app.get("/")
async def landing_page():
    return templates.TemplateResponse("landing.html", {"request": {}})

@app.get("/visualize")
async def visualize_page():
    # Fetch data from Neo4j
    with driver.session() as session:
        result = session.run(CYPHER_QUERY)
        raw_data = [record.data() for record in result]
        print(raw_data, "RAW DATA")
    
    # Process the data
    processed_data = []
    for row in raw_data:
        entry = {
            'ADC_Name': row['ADC_Name'],
            'Dosage': row['Dosage'],
            'PK_Parameters': [],  # Initialize as empty list
            'Adverse_Events': []  # Initialize as empty list
        }
        
        # Process PK data
        pk_data_mapping = {
            'CMAX_Data': 'Cmax',
            'TMAX_Data': 'Tmax',
            'AUC_Data': 'AUC',
            'AUCLAST_Data': 'AUClast',
            'THALF_Data': 'Thalf'
        }
        
        # Process each PK parameter type
        for raw_key, param_name in pk_data_mapping.items():
            if raw_key in row and isinstance(row[raw_key], list):
                for pk_item in row[raw_key]:
                    if isinstance(pk_item, dict):
                        value = pk_item.get('value', '')
                        
                        # Handle special cases where value contains multiple measurements
                        if isinstance(value, str) and '(' in value and ')' in value:
                            if 'AUCinf' in value:
                                value = value.split('AUCinf)')[0].split('(')[-1].strip()
                            elif 'AUClast' in value:
                                value = value.split('AUClast)')[0].split('(')[-1].strip()
                        
                        # Only add if we have valid data
                        if value and value != 'NOT FOUND':
                            entry['PK_Parameters'].append({
                                'parameter': param_name,
                                'analyte': pk_item.get('analyte', ''),
                                'value': value,
                                'unit': pk_item.get('unit', '') if pk_item.get('unit') != 'NOT FOUND' else ''
                            })
        
        # Process adverse events
        if isinstance(row.get('Adverse_Events'), list):
            for ae in row['Adverse_Events']:
                if isinstance(ae, dict):
                    event = ae.get('event', '')
                    if event and event != 'NOT FOUND':
                        entry['Adverse_Events'].append({
                            'event': event,
                            'grade': ae.get('grade', 'NOT FOUND'),
                            'count': ae.get('count', 'NOT FOUND'),
                            'percent': ae.get('percent', 'NOT FOUND'),
                            'related': ae.get('related', 'NOT FOUND')
                        })
        
        processed_data.append(entry)
    
    # Get unique ADC names
    unique_adcs = sorted(list(set(entry['ADC_Name'] for entry in processed_data)))
    
    # Generate plots
    plots = []
    
    # Get all unique adverse events that have AUC data
    available_aes = set()
    for record in processed_data:
        for ae in record['Adverse_Events']:
            if any(param['parameter'] == 'AUC' for param in record['PK_Parameters']):
                available_aes.add(ae['event'])
    
    # Sort the list of available AEs
    available_aes = sorted(list(available_aes))
    
    # Create plot for first available AE by default
    if available_aes:
        default_ae = available_aes[0]
        plots.append(create_auc_plot(processed_data, default_ae))
    
    # Create Dose vs Cmax plot
    plots.append(create_dose_cmax_plot(processed_data))
    
    # Get available units for each parameter type
    available_units = {
        'Cmax': get_available_units('Cmax'),
        'AUC': get_available_units('AUC')
    }
    
    return templates.TemplateResponse("index.html", {
        "request": {},
        "data": processed_data,
        "plots": plots,
        "available_aes": available_aes,
        "available_units": available_units,
        "unique_adcs": unique_adcs
    })

def clean_cypher_query(query: str) -> str:
    """Clean the Cypher query by removing markdown formatting."""
    # Remove markdown code block if present
    if query.startswith("```"):
        lines = query.splitlines()
        if len(lines) > 2:
            # Remove first and last lines (```cypher and ```)
            query = "\n".join(lines[1:-1])
    return query.strip()

def generate_neo4j_query(question: str) -> str:
    """Generate Neo4j query from natural language question using LLM."""
    prompt = f"""Given the following question about ADC (Antibody Drug Conjugate) data, generate a Neo4j Cypher query.
    The database has the following structure and properties:
    
    Nodes and their properties:
    - (adc:AntibodyDrugConjugate) with properties: id, name, createdAt, source_document_ref, doi_ref
    - (cohort:DosageCohort) with properties: id, name, createdAt, cohort_pk_notes, regimen_for_cohort, patients_in_cohort
    - (ae:AdverseEventTerm) with properties: id, name, createdAt
    - (pk:PK_Observation) with properties: id, createdAt, value, analyte_component, parameter_name, variability, unit, metric, auc_type_specified
    
    Relationships:
    - (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort:DosageCohort)
    - (cohort)-[r:HAS_AE]->(ae:AdverseEventTerm) with properties: patientPercentage, isDLT, grade, drugRelated, patientCount
    - (cohort)-[:HAS_AUC]->(pk:PK_Observation)
    - (cohort)-[:HAS_CMAX]->(pk:PK_Observation)
    - (cohort)-[:HAS_TMAX]->(pk:PK_Observation)
    - (cohort)-[:HAS_THALF]->(pk:PK_Observation)
    - (cohort)-[:HAS_AUCLAST]->(pk:PK_Observation)

    Example Queries:

// Q1: Get all the dosage cohorts across ADCs with Nausea as an AE.
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort:DosageCohort)-[r:HAS_AE]->(ae:AdverseEventTerm)
WHERE ae.name = 'Nausea'
RETURN adc.name AS ADC_Name, cohort.name AS Cohort_Dosage, r.grade AS Grade, r.patientPercentage AS Incidence, r.patientCount AS Patient_Count
ORDER BY ADC_Name, Cohort_Dosage;

//
// Q2: Find cohorts with no adverse events.
MATCH (c:DosageCohort)
WHERE NOT EXISTS((c)-[:HAS_AE]->(:AdverseEventTerm))
RETURN c.id, c.name
ORDER BY c.name;

//
// Q3: Get PK parameters for a specific ADC.
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort:DosageCohort)
WHERE adc.name CONTAINS 'T-DM1'
OPTIONAL MATCH (cohort)-[:HAS_CMAX]->(cmax:PK_Observation)
OPTIONAL MATCH (cohort)-[:HAS_TMAX]->(tmax:PK_Observation)
RETURN adc.name AS ADC_Name, cohort.name AS Dosage, cmax.value AS Cmax_Value, cmax.unit AS Cmax_Unit, tmax.value AS Tmax_Value, tmax.unit AS Tmax_Unit
ORDER BY Dosage;

//
// Q4: See a high-level count of all data types.
MATCH (n)
RETURN labels(n) AS NodeType, count(n) AS Count
ORDER BY Count DESC;

//
// Q5: List all ADCs and their main components.
MATCH (adc:AntibodyDrugConjugate)
OPTIONAL MATCH (adc)-[:HAS_TARGET]->(target:TargetAntigen)
OPTIONAL MATCH (adc)-[:USES_PAYLOAD_AGENT]->(payload:PayloadAgent)
OPTIONAL MATCH (adc)-[:HAS_LINKER_TYPE]->(linker:LinkerType)
RETURN adc.name AS ADC, target.name AS Target, payload.name AS Payload, linker.name AS Linker
ORDER BY ADC;

//
// Q6: Find which studies investigated which ADCs.
MATCH (study:Study)-[:INVESTIGATES_ADC]->(adc:AntibodyDrugConjugate)
RETURN study.study_identifier AS StudyID, study.title AS StudyTitle, adc.name AS ADC_Investigated;

//
// Q7: Find the most common adverse events across all studies.
MATCH ()-[r:HAS_AE]->(ae:AdverseEventTerm)
RETURN ae.name AS AdverseEvent, count(r) AS NumberOfTimesReported
ORDER BY NumberOfTimesReported DESC
LIMIT 15;

//
// Q8: Find all Dose-Limiting Toxicities (DLTs) for a ADC named .
MATCH (adc:AntibodyDrugConjugate {{name: 'Your_ADC_Name_Here'}})-[:HAS_COHORT]->(cohort)-[r:HAS_AE]->(ae:AdverseEventTerm)
WHERE r.isDLT = "True"
RETURN cohort.name AS Dosage, ae.name AS DoseLimitingToxicity, r.grade AS Grade, r.patientCount AS PatientCount
ORDER BY toInteger(r.grade) DESC;

//
// Q9: Find high-grade (Grade 3+) adverse events associated with a specific payload.
MATCH (payload:PayloadAgent {{name: 'MMAE'}})<-[:USES_PAYLOAD_AGENT]-(adc)-[:HAS_COHORT]->(cohort)-[r:HAS_AE]->(ae:AdverseEventTerm)
WHERE toInteger(r.grade) >= 3
RETURN adc.name AS ADC, cohort.name AS Dosage, ae.name AS HighGradeAE, r.grade AS Grade
ORDER BY ADC, Grade DESC;

//
// Q10: Find all ADCs that use a specific linker type.
MATCH (adc:AntibodyDrugConjugate)-[:HAS_LINKER_TYPE]->(linker:LinkerType)
WHERE linker.name CONTAINS 'cleavable'
RETURN adc.name AS ADC, linker.name AS LinkerType;

//
// Q11: Compare the Cmax values for two different ADCs.
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort)-[]->(pk:PK_Observation)
WHERE adc.name IN ['ADC_Name_1', 'ADC_Name_2'] AND pk.parameter_name = 'Cmax'
RETURN adc.name AS ADC, cohort.name AS Dosage, pk.value AS Cmax_Value, pk.unit AS Unit
ORDER BY ADC, toFloat(pk.value) DESC;

//
// Q12: Quickly identify cohorts where no adverse events were recorded.
MATCH (c:DosageCohort)
WHERE NOT (c)-[:HAS_AE]->()
RETURN c.name AS Cohort_Without_AE_Data;

//
// Q13: Find drugs in your database that are missing a relationship to a key component, like a payload.
MATCH (adc:AntibodyDrugConjugate)
WHERE NOT (adc)-[:USES_PAYLOAD_AGENT]->()
RETURN adc.name AS ADC_Missing_Payload_Info;

//
// Q14: Get a comprehensive table of PK parameters and adverse events for ADCs and their cohorts.
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort:DosageCohort)
OPTIONAL MATCH (cohort)-->(pk:PK_Observation)
OPTIONAL MATCH (cohort)-[ae_rel:HAS_AE]->(ae:AdverseEventTerm)
WITH adc, cohort,
     collect(DISTINCT {{
         parameter: pk.parameter_name,
         analyte: pk.analyte_component,
         value: pk.value,
         unit: pk.unit
     }}) AS pk_data,
     collect(DISTINCT {{
         event: ae.name,
         grade: ae_rel.grade,
         count: ae_rel.patientCount,
         percent: ae_rel.patientPercentage,
         related: ae_rel.drugRelated
     }}) AS ae_data
RETURN adc.name AS ADC_Name, cohort.name AS Dosage,
       [item IN pk_data WHERE item.parameter IS NOT NULL] AS PK_Parameters,
       [item IN ae_data WHERE item.event IS NOT NULL] AS Adverse_Events
ORDER BY ADC_Name, Dosage;

//
// Q15: Identify adverse event (AE) incidence based on dose exposure and compare across different ADCs.
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort:DosageCohort)-[r:HAS_AE]->(ae:AdverseEventTerm)
WHERE r.patientPercentage IS NOT NULL AND r.patientPercentage <> 'NOT FOUND' AND r.patientPercentage <> ''
RETURN adc.name AS ADC, ae.name AS AdverseEvent, cohort.name AS DoseLevel,
       toFloat(split(cohort.name, ' ')[0]) AS DoseValue,
       toFloat(replace(r.patientPercentage, '%', '')) AS IncidencePercentage,
       r.grade AS Grade
ORDER BY ADC, AdverseEvent, DoseValue;

//
// Q16: Do ADCs with the same payload cause similar side effects, even if their targets are different?
MATCH (payload:PayloadAgent)<-[:USES_PAYLOAD_AGENT]-(adc1:AntibodyDrugConjugate),
      (payload)<-[:USES_PAYLOAD_AGENT]-(adc2:AntibodyDrugConjugate)
WHERE adc1 <> adc2
MATCH (adc1)-[:HAS_COHORT]->()-[r1:HAS_AE]->(ae:AdverseEventTerm),
      (adc2)-[:HAS_COHORT]->()-[r2:HAS_AE]->(ae)
RETURN payload.name AS SharedPayload, adc1.name AS ADC1, adc2.name AS ADC2, ae.name AS CommonAdverseEvent
ORDER BY SharedPayload, CommonAdverseEvent;

//
// Q17: Analyze the AE profile for a drug based on its study phase.
MATCH (phase:StudyPhase)<-[:HAS_STUDY_PHASE]-(study:Study)-[:INVESTIGATES_ADC]->(adc:AntibodyDrugConjugate),
      (study)-[:INCLUDES_COHORT]->(cohort:DosageCohort)-[r:HAS_AE]->(ae:AdverseEventTerm)
WHERE r.patientPercentage IS NOT NULL AND r.patientPercentage <> 'NOT FOUND'
RETURN adc.name AS ADC, phase.name AS StudyPhase, ae.name AS AdverseEvent,
       avg(toFloat(replace(r.patientPercentage, '%', ''))) AS AvgIncidenceInPhase
ORDER BY ADC, AdverseEvent, StudyPhase;

//
// Q18: List all ADCs currently in a specific phase of development.
MATCH (adc:AntibodyDrugConjugate)<-[:INVESTIGATES_ADC]-(study:Study)-[:HAS_STUDY_PHASE]->(phase:StudyPhase)
WHERE phase.name CONTAINS '2'
RETURN DISTINCT adc.name AS ADC_In_Phase_2, study.study_identifier AS StudyID, study.title AS StudyTitle;

//
// Q19: Find the dose at which an AE of special interest first appears at a clinically significant rate.
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort)-[r:HAS_AE]->(ae:AdverseEventTerm {{name: 'Neutropenia'}})
WHERE toFloat(replace(r.patientPercentage, '%', '')) > 10
WITH adc, cohort, toFloat(split(cohort.name, ' ')[0]) AS doseValue
RETURN adc.name AS ADC, min(doseValue) AS FirstDoseForAE_Over10Percent
ORDER BY ADC;

// Q20: How does the Cmax of the ADC analyte change as the dose increases for Trastuzumab deruxtecan (DS-8201)?
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort)-[:HAS_CMAX]->(pk:PK_Observation)
WHERE adc.name CONTAINS 'Trastuzumab deruxtecan (DS-8201)' AND pk.analyte_component = 'ADC'
RETURN
    adc.name AS ADC,
    cohort.name AS Cohort_Dose,
    toFloat(pk.value) AS Cmax_Value
ORDER BY Cmax_Value;

// Q21: How does the AUC (Area Under the Curve) for the main ADC analyte compare between T-DM1 and Polatuzumab vedotin (pola)?
MATCH (adc:AntibodyDrugConjugate)-[:HAS_COHORT]->(cohort)-[:HAS_AUC]->(pk:PK_Observation)
WHERE adc.name IN ['Trastuzumab emtansine (T-DM1)', 'Polatuzumab vedotin (pola)'] AND pk.analyte_component = 'ADC'
RETURN
    adc.name AS ADC,
    cohort.name AS Cohort_Dose,
    pk.value AS AUC_Value,
    pk.unit AS Unit
ORDER BY ADC, toFloat(pk.value);

// Q22: Give me all general AEs in ADC: Sacituzumab govitecan (SG, IMMU-132)
MATCH (study:Study)-[:INVESTIGATES_ADC]->(adc:AntibodyDrugConjugate)
WHERE adc.name CONTAINS 'Sacituzumab govitecan (SG, IMMU-132)'
RETURN
    adc.name AS ADC,
    study.generalAEsMentioned AS General_Adverse_Events;

// Q23: Analyze the AE profile for a drug based on its study phase
MATCH (phase:StudyPhase)<-[:HAS_STUDY_PHASE]-(study:Study)-[:INVESTIGATES_ADC]->(adc:AntibodyDrugConjugate),
      (study)-[:INCLUDES_COHORT]->(cohort:DosageCohort)-[r:HAS_AE]->(ae:AdverseEventTerm)
WHERE r.patientPercentage IS NOT NULL AND r.patientPercentage <> 'NOT FOUND'
RETURN
    adc.name AS ADC,
    phase.name AS StudyPhase,
    ae.name AS AdverseEvent,
    avg(toFloat(replace(r.patientPercentage, '%', ''))) AS AvgIncidenceInPhase
ORDER BY ADC, AdverseEvent, StudyPhase;

    ```

Question: {question}
    
    Generate a Cypher query that will answer this question. Return only the query, no explanations.
    Make sure to:
    1. Use the correct property names as listed above
    2. Include appropriate WHERE clauses for filtering
    3. Use OPTIONAL MATCH when appropriate
    4. Order results logically
    5. Give clear column aliases using AS
    """
    
    response = model.generate_content(prompt)
    return clean_cypher_query(response.text)

def analyze_neo4j_results(results: List[Dict], question: str) -> str:
    """Analyze Neo4j results and generate user-friendly response using LLM."""
    results_str = json.dumps(results, indent=2)
    
    # Step 2: Generate response using LLM
    prompt = f"""
You are a friendly and helpful research assistant named <strong>Vantage</strong>. Your task is to provide clear, structured, and visually rich answers using proper HTML formatting wherever appropriate.
Original Question: {question}
These are the answers for the question:
{results_str}
Please format your response using the exact structure below. Wrap all content inside a container div:
<div class="llm-response" style="width: 90%;">
🔍 <strong>Summary</strong>  
<p>Write a brief summary of 1–2 sentences introducing the key insight or finding.</p>
📊 <strong>Data Overview</strong>  
<p>Use appropriate HTML tags to present the data clearly:</p>
<ul>
<li>
  If the data is structured, use a <code>&lt;table&gt;</code> with 
  <code>&lt;thead&gt;</code>, <code>&lt;tbody&gt;</code>, 
  <code>&lt;tr&gt;</code>, <code>&lt;th&gt;</code>, and 
  <code>&lt;td&gt;</code>. Add <code>border="1"</code> and 
  <code>cellpadding="6"</code> for styling. 
  Style the header row with 
  <code>style="background-color: #333; color: white;"</code> 
  on the <code>&lt;th&gt;</code> or <code>&lt;tr&gt;</code> inside <code>&lt;thead&gt;</code>.
</li>
  <li>For lists, use <code>&lt;ul&gt;</code> or <code>&lt;ol&gt;</code> as appropriate.</li>
  <li>Highlight key values using: <code>&lt;span style="color: red; font-weight: bold"&gt;Important Value&lt;/span&gt;</code>.</li>
  <li>Wrap any explanatory text in <code>&lt;p&gt;</code> tags.</li>
  <li>Avoid excessive use of <code>&lt;br&gt;</code> tags. Use semantic structure instead.</li>
</ul>
⚡ <strong>Key Findings</strong>  
<ul>
  <li>Provide up to three concise, non-redundant bullet points summarizing key insights.</li>
</ul>
</div>
"""
    
    response = model.generate_content(prompt)
    return response.text.strip()

@app.post("/ask")
async def ask_chatbot(question: UserQuery):
    """Handle chatbot questions with a two-step LLM process."""
    try:
        # Step 1: Generate Neo4j query using LLM
        neo4j_query = generate_neo4j_query(question.question)
        print(f"Generated Neo4j query: {neo4j_query}")
        
        # Step 2: Execute the query
        with driver.session() as session:
            result = session.run(neo4j_query)
            results = [record.data() for record in result]
        
        # Step 3: Analyze results using LLM
        if results:
            analysis = analyze_neo4j_results(results, question.question)
            return {"results": [{"message": analysis}]}
        else:
            return {"results": [{"message": "No results found for your query."}]}

    except Exception as e:
        print(f"Error in ask_chatbot: {str(e)}")
        return {"results": [{"type": "error", "message": f"Error processing your question: {str(e)}"}]}

@app.get("/update-plot")
async def update_plot(ae: str = None, unit: str = None, type: str = None):
    try:
        with driver.session() as session:
            result = session.run(CYPHER_QUERY)
            raw_data = [record.data() for record in result]

        # Process data similar to the main endpoint
        processed_data = []
        for row in raw_data:
            entry = {
                'ADC_Name': row['ADC_Name'],
                'Dosage': row['Dosage'],
                'PK_Parameters': [],
                'Adverse_Events': []
            }
            
            # Process PK data
            pk_data_mapping = {
                'CMAX_Data': 'Cmax',
                'TMAX_Data': 'Tmax',
                'AUC_Data': 'AUC',
                'AUCLAST_Data': 'AUClast',
                'THALF_Data': 'Thalf'
            }
            
            for raw_key, param_name in pk_data_mapping.items():
                if raw_key in row and isinstance(row[raw_key], list):
                    for pk_item in row[raw_key]:
                        if isinstance(pk_item, dict):
                            value = pk_item.get('value', '')
                            if value and value != 'NOT FOUND':
                                entry['PK_Parameters'].append({
                                    'parameter': param_name,
                                    'analyte': pk_item.get('analyte', ''),
                                    'value': value,
                                    'unit': pk_item.get('unit', '') if pk_item.get('unit') != 'NOT FOUND' else ''
                                })
            
            # Process adverse events
            if isinstance(row.get('Adverse_Events'), list):
                for ae_item in row['Adverse_Events']:
                    if isinstance(ae_item, dict):
                        event = ae_item.get('event', '')
                        if event and event != 'NOT FOUND':
                            entry['Adverse_Events'].append({
                                'event': event,
                                'grade': ae_item.get('grade', 'NOT FOUND'),
                                'count': ae_item.get('count', 'NOT FOUND'),
                                'percent': ae_item.get('percent', 'NOT FOUND'),
                                'related': ae_item.get('related', 'NOT FOUND')
                            })
            
            processed_data.append(entry)

        # Get unique ADC names for consistent colors
        unique_adcs = list(set(entry['ADC_Name'].lower().strip() for entry in processed_data))
        colors = plt.cm.Set3(np.linspace(0, 1, len(unique_adcs)))
        adc_colors = dict(zip(unique_adcs, colors))

        if type == 'cmax':
            # Create Cmax plot with selected unit
            fig, ax = plt.subplots(figsize=(10, 6))
            plotted_adcs = set()
            
            for entry in processed_data:
                try:
                    dose = float(entry['Dosage'].split()[0])
                    cmax_data = next((pk for pk in entry['PK_Parameters'] if pk['parameter'] == 'Cmax'), None)
                    if cmax_data and cmax_data.get('value'):
                        cmax_value = float(cmax_data['value'])
                        from_unit = cmax_data.get('unit', 'µg/mL')
                        cmax_value = convert_unit(cmax_value, from_unit, unit, 'Cmax')
                        
                        normalized_name = entry['ADC_Name'].lower().strip()
                        color = adc_colors[normalized_name]
                        label = entry['ADC_Name'] if normalized_name not in plotted_adcs else None
                        ax.scatter(dose, cmax_value, label=label, color=color)
                        plotted_adcs.add(normalized_name)
                except (ValueError, TypeError, IndexError):
                    continue
            
            ax.set_xlabel('Dose (mg/kg)')
            ax.set_ylabel(f'Cmax ({unit})')
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            plt.tight_layout()
            
            # Convert plot to base64
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            plot_base64 = base64.b64encode(buf.read()).decode('utf-8')
            plt.close(fig)
            
            return JSONResponse({"plot_data": plot_base64})
            
        elif type == 'auc' and ae:
            # Create AUC plot with selected unit and AE
            fig, ax = plt.subplots(figsize=(10, 6))
            plotted_adcs = set()
            
            for entry in processed_data:
                # Look for both AUC and AUCinf in PK parameters
                auc_data = next((pk for pk in entry['PK_Parameters'] 
                               if pk['parameter'] in ['AUC', 'AUCinf'] 
                               and pk['analyte'] == 'ADC'), None)
                
                ae_data = next((ae_item for ae_item in entry['Adverse_Events'] 
                              if ae_item['event'] == ae), None)
                
                if auc_data and auc_data.get('value') and ae_data and ae_data.get('percent'):
                    try:
                        # Clean and convert AUC value
                        auc_value = str(auc_data['value']).strip()
                        if '(' in auc_value and ')' in auc_value:
                            # Extract value from parentheses if present
                            auc_value = auc_value.split('(')[-1].split(')')[0].strip()
                        
                        auc_value = float(auc_value)
                        
                        # Convert to selected unit
                        from_unit = auc_data.get('unit', 'µg*day/mL')
                        if from_unit == 'NOT FOUND':
                            from_unit = 'µg*day/mL'
                        auc_value = convert_unit(auc_value, from_unit, unit, 'AUC')
                        
                        # Clean and convert percentage
                        percent_str = str(ae_data['percent']).strip()
                        if percent_str.endswith('%'):
                            percent_str = percent_str[:-1]
                        percent = float(percent_str)
                        
                        normalized_name = entry['ADC_Name'].lower().strip()
                        color = adc_colors[normalized_name]
                        label = entry['ADC_Name'] if normalized_name not in plotted_adcs else None
                        ax.scatter(auc_value, percent, label=label, color=color)
                        plotted_adcs.add(normalized_name)
                    except (ValueError, TypeError) as e:
                        print(f"Error processing data point: {str(e)}")
                        continue
            
            if plotted_adcs:
                ax.set_xlabel(f'AUC ({unit})')
                ax.set_ylabel(f'{ae} (%)')
                ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
                plt.tight_layout()
                
                # Convert plot to base64
                buf = io.BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight')
                buf.seek(0)
                plot_base64 = base64.b64encode(buf.read()).decode('utf-8')
                plt.close(fig)
                
                return JSONResponse({"plot_data": plot_base64})
            else:
                raise HTTPException(status_code=404, detail="No data available for the selected AE")
        else:
            raise HTTPException(status_code=400, detail="Invalid request parameters")
            
    except Exception as e:
        print(f"Error in update_plot: {str(e)}")  # Add logging
        raise HTTPException(status_code=500, detail=str(e))

def create_auc_plot(data, selected_ae):
    # Get unique ADC names for consistent colors
    unique_adcs = list(set(entry['ADC_Name'].lower().strip() for entry in data))
    colors = plt.cm.Set3(np.linspace(0, 1, len(unique_adcs)))
    adc_colors = dict(zip(unique_adcs, colors))
    
    fig, ax = plt.subplots(figsize=(10, 6))
    plotted_adcs = set()
    
    for entry in data:
        # Look for both AUC and AUCinf in PK parameters
        auc_data = next((pk for pk in entry['PK_Parameters'] 
                        if pk['parameter'] in ['AUC', 'AUCinf'] 
                        and pk['analyte'] == 'ADC'), None)
        
        ae = next((ae for ae in entry['Adverse_Events'] 
                  if ae['event'] == selected_ae), None)
        
        if auc_data and auc_data.get('value') and ae and ae.get('percent'):
            try:
                # Clean and convert AUC value
                auc_value = str(auc_data['value']).strip()
                if '(' in auc_value and ')' in auc_value:
                    # Extract value from parentheses if present
                    auc_value = auc_value.split('(')[-1].split(')')[0].strip()
                
                auc_value = float(auc_value)
                
                # Convert to default unit (µg*day/mL)
                from_unit = auc_data.get('unit', 'µg*day/mL')
                if from_unit == 'NOT FOUND':
                    from_unit = 'µg*day/mL'
                auc_value = convert_unit(auc_value, from_unit, 'µg*day/mL', 'AUC')
                
                # Clean and convert percentage
                percent_str = str(ae['percent']).strip()
                if percent_str.endswith('%'):
                    percent_str = percent_str[:-1]
                percent = float(percent_str)
                
                normalized_name = entry['ADC_Name'].lower().strip()
                color = adc_colors[normalized_name]
                label = entry['ADC_Name'] if normalized_name not in plotted_adcs else None
                ax.scatter(auc_value, percent, label=label, color=color)
                plotted_adcs.add(normalized_name)
            except (ValueError, TypeError) as e:
                print(f"Error processing data point: {str(e)}")
                continue
    
    if plotted_adcs:  # Only add plot if we have data
        ax.set_xlabel('AUC (µg*day/mL)')
        ax.set_ylabel(f'{selected_ae} (%)')
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        return (f'AUC vs {selected_ae}', plot_to_base64(fig))
    
    plt.close(fig)
    return None

def create_dose_cmax_plot(data):
    # Get unique ADC names for consistent colors
    unique_adcs = list(set(entry['ADC_Name'].lower().strip() for entry in data))
    colors = plt.cm.Set3(np.linspace(0, 1, len(unique_adcs)))
    adc_colors = dict(zip(unique_adcs, colors))
    
    fig, ax = plt.subplots(figsize=(10, 6))
    plotted_adcs = set()
    
    for entry in data:
        try:
            dose = float(entry['Dosage'].split()[0])  # Extract first number from dosage
            cmax_data = next((pk for pk in entry['PK_Parameters'] if pk['parameter'] == 'Cmax'), None)
            if cmax_data and cmax_data.get('value'):
                cmax_value = float(cmax_data['value'])
                # Convert to default unit (µg/mL)
                from_unit = cmax_data.get('unit', 'µg/mL')
                cmax_value = convert_unit(cmax_value, from_unit, 'µg/mL', 'Cmax')
                
                normalized_name = entry['ADC_Name'].lower().strip()
                color = adc_colors[normalized_name]
                label = entry['ADC_Name'] if normalized_name not in plotted_adcs else None
                ax.scatter(dose, cmax_value, label=label, color=color)
                plotted_adcs.add(normalized_name)
        except (ValueError, TypeError, IndexError):
            continue
    
    ax.set_xlabel('Dose (mg/kg)')
    ax.set_ylabel('Cmax (µg/mL)')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    return ('Dose vs Cmax', plot_to_base64(fig))
