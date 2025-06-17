import google.generativeai as genai
from app.core.config import settings
from typing import List, Dict, Any

class GeminiService:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    async def generate_cypher(self, question: str, schema_hint: str = "") -> str:
        prompt = f"""
You are a Cypher expert specializing in medical and pharmaceutical data analysis.
Given a user's natural language question, convert it into a Cypher query that will extract relevant insights.
Follow these guidelines:
1. Use only the relationships and node types provided in the schema
2. Return meaningful properties that will help answer the question
3. Include appropriate aggregations and filters
4. Format the query for readability

Schema: {schema_hint}

Question: {question}

Generate a Cypher query that will help answer this question. Only return the Cypher query without any explanations.
"""
        response = self.model.generate_content(prompt)
        return response.text.strip()

    def _format_metadata(self, data: Dict[str, Any]) -> str:
        """Format metadata into a readable text format."""
        if not data:
            return ""
            
        formatted_text = []
        
        # Format study information if present
        if 's' in data:
            study = data['s']
            formatted_text.append("Study Information:")
            if 'title' in study:
                formatted_text.append(f"• Title: {study['title']}")
            if 'study_identifier' in study:
                formatted_text.append(f"• Study ID: {study['study_identifier']}")
            if 'doi' in study:
                formatted_text.append(f"• DOI: {study['doi']}")
            if 'source_document_ref' in study:
                formatted_text.append(f"• Source: {study['source_document_ref']}")
            formatted_text.append("")  # Add blank line
            
        # Format ADC information if present
        if 'adc' in data:
            adc = data['adc']
            formatted_text.append("ADC Information:")
            if 'name' in adc:
                formatted_text.append(f"• Name: {adc['name']}")
            if 'source_document_ref' in adc:
                formatted_text.append(f"• Source: {adc['source_document_ref']}")
            if 'doi_ref' in adc:
                formatted_text.append(f"• DOI: {adc['doi_ref']}")
                
        return "\n".join(formatted_text)

    def _generate_natural_insights(self, data: List[Dict[str, Any]], query: str) -> str:
        """Generate natural language insights from the data."""
        try:
            # Extract key information
            adc_groups = {}
            for item in data:
                adc_name = item.get('ADC name', '')
                if adc_name not in adc_groups:
                    adc_groups[adc_name] = []
                adc_groups[adc_name].append(item)

            # Create a natural language prompt
            context = """You are an expert in analyzing pharmacokinetic and clinical data. 
            Please provide insights about this data in a conversational, easy-to-understand way.
            Focus on:
            1. Key findings for each ADC and dosage level
            2. Notable patterns in PK parameters
            3. Important safety observations from adverse events
            4. Comparisons between different dosage levels
            5. Practical implications for treatment

            Keep the language simple and avoid technical jargon.
            Structure the response in clear paragraphs with natural transitions.
            Don't mention that you're an AI or that you're analyzing data."""

            # Format the data in a way that's easier for the model to understand
            summary_points = []
            for adc_name, items in adc_groups.items():
                summary_points.append(f"For {adc_name}:")
                for item in items:
                    dosage = item.get('Dosage Cohort', '')
                    summary_points.append(f"- At {dosage}:")
                    
                    # Add PK parameters if available
                    pk_info = []
                    if item.get('Cmax ADC'):
                        pk_info.append(f"Maximum concentration was {item['Cmax ADC']}")
                    if item.get('Thalf ADC'):
                        pk_info.append(f"Half-life was {item['Thalf ADC']}")
                    if pk_info:
                        summary_points.append("  " + "; ".join(pk_info))
                    
                    # Add adverse events if available
                    ae_info = []
                    for key, value in item.items():
                        if any(ae in key.lower() for ae in ['nausea', 'vomiting', 'fatigue', 'anemia']):
                            if value and value != "NA":
                                ae_info.append(f"{key}: {value}%")
                    if ae_info:
                        summary_points.append("  Adverse events: " + ", ".join(ae_info))

            # Create the final prompt
            prompt = f"""{context}

Key Information:
{chr(10).join(summary_points)}

User's Question: {query}

Please provide a natural, conversational response focusing on the most relevant aspects to the user's question."""

            # Generate response using Gemini
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            
            return response.text.strip()

        except Exception as e:
            print(f"Error generating insights: {str(e)}")
            return "I apologize, but I couldn't generate insights from the data at this moment. Please try again or rephrase your question."

    def _extract_study_info(self, data: Dict[str, Any]) -> str:
        """Extract study information in a conversational format."""
        if not data or 's' not in data:
            return ""
            
        study = data['s']
        info = []
        
        if study.get('title'):
            info.append(f"Based on the study '{study['title']}'")
        if study.get('study_identifier'):
            info.append(f"(Study ID: {study['study_identifier']})")
        
        return " ".join(info) if info else ""

    def _format_study_findings(self, data: List[Dict[str, Any]]) -> str:
        """Format study findings in a conversational way."""
        if not data:
            return "I don't have any study data to analyze at the moment."
            
        findings = []
        current_adc = None
        
        for item in data:
            adc_name = item.get('ADC name')
            if not adc_name:
                continue
                
            if adc_name != current_adc:
                current_adc = adc_name
                findings.append(f"\nRegarding {adc_name}:")
            
            dosage = item.get('Dosage Cohort')
            if not dosage:
                continue
                
            findings.append(f"\nAt {dosage}:")
            
            # Add PK parameters in natural language
            pk_info = []
            if item.get('Cmax ADC'):
                pk_info.append(f"reached a maximum concentration of {item['Cmax ADC']}")
            if item.get('Tmax ADC'):
                pk_info.append(f"took {item['Tmax ADC']} hours to reach peak concentration")
            if item.get('Thalf ADC'):
                pk_info.append(f"had a half-life of {item['Thalf ADC']}")
            
            if pk_info:
                findings.append("The drug " + ", and ".join(pk_info) + ".")
            
            # Add adverse events in natural language
            ae_events = []
            for key in ['Nausea', 'Vomiting', 'Fatigue', 'Anemia']:
                if item.get(key) and item[key] != "NA":
                    ae_events.append(f"{item[key]}% of patients experienced {key.lower()}")
            
            if ae_events:
                findings.append("In terms of side effects, " + ", and ".join(ae_events) + ".")
        
        return "\n".join(findings)

    def generate_response(self, query: str, results: List[Dict[str, Any]]) -> str:
        """Generate a natural language response about the study and findings."""
        try:
            # Start with study context if available
            if results and isinstance(results[0], dict):
                study_context = self._extract_study_info(results[0])
            else:
                study_context = ""
            
            # Get the findings in natural language
            findings = self._format_study_findings(results)
            
            # Create a natural prompt for Gemini to generate insights
            prompt = f"""Based on this clinical study information:

{study_context}

And these findings:
{findings}

User's question: {query}

Please provide a clear, conversational analysis that:
1. Addresses the user's specific question
2. Highlights key patterns and relationships
3. Uses simple, non-technical language
4. Focuses on practical implications
5. Avoids mentioning data structures or technical details

Keep the response natural and easy to understand."""

            # Generate the final response
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            
            # Return only the natural language response
            return response.text.strip()
            
        except Exception as e:
            print(f"Error in response generation: {str(e)}")
            return "I apologize, but I'm having trouble analyzing the study data right now. Could you please try asking your question again?"

    def _format_table(self, data: List[Dict[str, Any]]) -> str:
        """Format data as an HTML table with specific styling."""
        if not data:
            return "No data available"
            
        # Define the column structure
        pk_params = {
            'Tmax': {'unit': ''},  # No specific unit for Tmax
            'Cmax': {'unit': 'µg/mL'},
            'AUCinf': {'unit': 'day µg/mL'},
            'AUClast': {'unit': ''},
            'Thalf': {'unit': 'days'}
        }
        pk_columns = list(pk_params.keys())
        adc_columns = ['ADC', 'Free Payload', 'Total AB']
        
        # Extract adverse event columns (they end with %)
        ae_columns = []
        for key in data[0].keys():
            if '(%)' in key or key.endswith('%'):
                ae_columns.append(key)
        ae_columns.sort()
        
        # Create the table HTML with specific styling
        html = ['''<table class="data-table" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;">''']
        
        # First header row with main categories
        html.append('<tr>')
        html.append('<th colspan="2" style="border: 1px solid black;"></th>')  # Empty space for ADC name and Dosage Cohort
        html.append('<th colspan="15" style="border: 1px solid black; text-align: center; background-color: #f5f5f5;">PK Parameter</th>')
        html.append(f'<th colspan="{len(ae_columns)}" style="border: 1px solid black; text-align: center; background-color: #f5f5f5;">Adverse Event Terms %</th>')
        html.append('</tr>')
        
        # Second header row with PK parameter names
        html.append('<tr>')
        html.append('<th colspan="2" style="border: 1px solid black;"></th>')
        for pk in pk_columns:
            html.append(f'<th colspan="3" style="border: 1px solid black; text-align: center; background-color: #f5f5f5;">{pk}</th>')
        for ae in ae_columns:
            html.append(f'<th rowspan="2" style="border: 1px solid black; text-align: center; background-color: #f5f5f5;">{ae.replace(" (%)", "")}</th>')
        html.append('</tr>')
        
        # Third header row with sub-columns
        html.append('<tr>')
        html.append('<th style="border: 1px solid black; background-color: #f5f5f5;">ADC name</th>')
        html.append('<th style="border: 1px solid black; background-color: #f5f5f5;">Dosage Cohort</th>')
        for _ in pk_columns:
            for col in adc_columns:
                html.append(f'<th style="border: 1px solid black; text-align: center; background-color: #f5f5f5;">{col}</th>')
        html.append('</tr>')
        
        # Group data by ADC name
        adc_groups = {}
        for item in data:
            adc_name = item.get('ADC name', 'Unknown')
            if adc_name not in adc_groups:
                adc_groups[adc_name] = []
            adc_groups[adc_name].append(item)
        
        # Add data rows
        for adc_name, items in adc_groups.items():
            for i, item in enumerate(items):
                html.append('<tr>')
                
                # Add ADC name only for first row of each group
                if i == 0:
                    html.append(f'<td rowspan="{len(items)}" style="border: 1px solid black; padding: 8px;">{adc_name}</td>')
                
                # Add dosage cohort
                html.append(f'<td style="border: 1px solid black; padding: 8px;">{item.get("Dosage Cohort", "")}</td>')
                
                # Add PK parameters with units
                for pk in pk_columns:
                    for col in adc_columns:
                        key = f"{pk} {col}"
                        value = item.get(key, "NA")
                        if value != "NA" and pk_params[pk]['unit']:
                            if isinstance(value, (int, float)):
                                value = f"{value} {pk_params[pk]['unit']}"
                        html.append(f'<td style="border: 1px solid black; text-align: center; padding: 8px;">{value}</td>')
                
                # Add adverse events (percentages)
                for ae in ae_columns:
                    value = item.get(ae, "0")
                    if value != "NA":
                        value = str(value)  # Ensure it's a string
                        if not value.endswith('%'):
                            value = f"{value}"  # Don't add % as it's in the header
                    html.append(f'<td style="border: 1px solid black; text-align: center; padding: 8px;">{value}</td>')
                
                html.append('</tr>')
        
        html.append('</table>')
        
        return '\n'.join(html)

def format_basic_response(results):
    """Fallback function to format results in a basic way if LLM fails"""
    if not results:
        return "I couldn't find any data matching your query. Please try rephrasing your question."
    
    # If results is a list of dictionaries with the same keys
    if isinstance(results, list) and all(isinstance(r, dict) for r in results):
        if len(set(tuple(sorted(r.keys())) for r in results)) == 1:
            # Get the first key (assuming it's the main identifier)
            main_key = list(results[0].keys())[0]
            items = [r[main_key] for r in results]
            
            response = f"I found {len(items)} items:\n\n"
            for item in items:
                response += f"• {item}\n"
            
            # Add a summary and suggestions
            response += "\nThis is a complete list of all items found in the database. "
            response += "Would you like to know more about any specific item or see how these items relate to other data in the database?"
            return response
    
    # Default formatting for other cases
    response = "Here's what I found:\n\n"
    for result in results:
        if isinstance(result, dict):
            for key, value in result.items():
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        response += f"• {subkey}: {subvalue}\n"
                else:
                    response += f"• {key}: {value}\n"
        else:
            response += f"• {result}\n"
    
    return response

gemini_service = GeminiService() 