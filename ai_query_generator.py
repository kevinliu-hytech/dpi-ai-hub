"""
AI-Powered Query Generator using Claude API

This module uses Claude to convert natural language questions into SQL queries
and provide intelligent data analysis.
"""

import os
from anthropic import Anthropic
from query_loader import QueryKnowledgeBase
from typing import Dict, Any, Optional
import json


class AIQueryGenerator:
    """Generate SQL queries from natural language using Claude API"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the AI Query Generator

        Args:
            api_key: Anthropic API key. If not provided, will use ANTHROPIC_API_KEY env var
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

        self.client = Anthropic(api_key=self.api_key)
        self.kb = QueryKnowledgeBase()
        self.context = self.kb.get_context_for_ai()

    def generate_query(self, natural_language: str, conversation_history: list = None) -> Dict[str, Any]:
        """
        Convert natural language to SQL query

        Args:
            natural_language: The user's question in plain English
            conversation_history: Previous conversation messages for context

        Returns:
            Dict with 'sql', 'explanation', and 'confidence' keys
        """

        # Build the system prompt with database context
        system_prompt = f"""You are an expert SQL query generator for a business intelligence system.

# Database Context
{self.context}

# Important Guidelines
1. Generate MySQL-compatible SQL queries only
2. Always use proper table names from the context above
3. For STAR brand queries, use tables in gbis.biz schema
4. Include date filters when appropriate (data starts from 2025-01-01)
5. Use appropriate aggregations (SUM, COUNT, AVG) for metrics
6. Group by dimensions when aggregating
7. Order results by date DESC or by the main metric DESC
8. Add LIMIT clauses (default 100) unless specifically asked for all data
9. Use COALESCE for null handling when needed
10. Format currency and numbers appropriately

# Query Response Format
Return a JSON object with:
- sql: The generated SQL query
- explanation: Brief explanation of what the query does
- confidence: Your confidence level (high/medium/low)
- suggested_chart: Suggested chart type (bar/line/pie/scatter) or null
- x_column: Suggested X-axis column name or null
- y_column: Suggested Y-axis column name or null

# Example Response
{{
    "sql": "SELECT date, SUM(ftd) as total_ftd FROM gbis.biz.dashboard_star_fact_daily_kpi WHERE date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) GROUP BY date ORDER BY date DESC",
    "explanation": "Returns daily first-time deposits for the last 30 days",
    "confidence": "high",
    "suggested_chart": "line",
    "x_column": "date",
    "y_column": "total_ftd"
}}
"""

        # Build the conversation messages
        messages = conversation_history or []
        messages.append({
            "role": "user",
            "content": natural_language
        })

        try:
            # Call Claude API
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=system_prompt,
                messages=messages
            )

            # Parse the response
            content = response.content[0].text

            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                if '{' in content and '}' in content:
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1
                    json_str = content[json_start:json_end]
                    result = json.loads(json_str)
                else:
                    # If no JSON found, treat entire response as SQL
                    result = {
                        "sql": content.strip(),
                        "explanation": "Generated SQL query",
                        "confidence": "medium",
                        "suggested_chart": None,
                        "x_column": None,
                        "y_column": None
                    }
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                result = {
                    "sql": content.strip(),
                    "explanation": "Generated SQL query",
                    "confidence": "medium",
                    "suggested_chart": None,
                    "x_column": None,
                    "y_column": None
                }

            return {
                "success": True,
                **result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def analyze_data(self, query: str, data: list, question: str = None) -> Dict[str, Any]:
        """
        Analyze query results and provide insights

        Args:
            query: The SQL query that was executed
            data: The query results as list of dictionaries
            question: Optional original question for context

        Returns:
            Dict with 'analysis', 'insights', and 'recommendations'
        """

        # Prepare data summary
        row_count = len(data)
        sample_data = data[:5] if len(data) > 5 else data

        system_prompt = """You are a business intelligence analyst providing insights on data.

Analyze the query results and provide:
1. Key findings and trends
2. Notable patterns or anomalies
3. Actionable recommendations
4. Business implications

Keep your analysis concise, focused, and actionable."""

        user_prompt = f"""Original Question: {question or 'Not provided'}

SQL Query:
```sql
{query}
```

Results Summary:
- Total Rows: {row_count}
- Sample Data (first 5 rows):
{json.dumps(sample_data, indent=2, default=str)}

Please analyze this data and provide insights."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            analysis = response.content[0].text

            return {
                "success": True,
                "analysis": analysis
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def refine_query(self, original_query: str, error_message: str, natural_language: str) -> Dict[str, Any]:
        """
        Attempt to fix a failed query based on error message

        Args:
            original_query: The SQL query that failed
            error_message: The error message from the database
            natural_language: Original user question

        Returns:
            Dict with refined 'sql' and 'explanation'
        """

        system_prompt = f"""You are an expert SQL debugger. Fix the broken SQL query based on the error message.

# Database Context
{self.context}

Return a JSON object with:
- sql: The corrected SQL query
- explanation: What was wrong and how you fixed it
- confidence: Your confidence in the fix (high/medium/low)
"""

        user_prompt = f"""Original Question: {natural_language}

Failed Query:
```sql
{original_query}
```

Error Message:
{error_message}

Please fix the query."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            content = response.content[0].text

            # Try to extract JSON
            if '{' in content and '}' in content:
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                json_str = content[json_start:json_end]
                result = json.loads(json_str)
            else:
                result = {
                    "sql": content.strip(),
                    "explanation": "Attempted to fix the query",
                    "confidence": "low"
                }

            return {
                "success": True,
                **result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Convenience function for easy import
def create_generator(api_key: Optional[str] = None) -> AIQueryGenerator:
    """Create an AI Query Generator instance"""
    return AIQueryGenerator(api_key)


if __name__ == "__main__":
    # Test the generator
    print("Testing AI Query Generator...")

    try:
        generator = AIQueryGenerator()

        # Test query generation
        result = generator.generate_query(
            "Show me daily FTD count for STAR brand in the last 7 days"
        )

        if result['success']:
            print("\n✓ Query generated successfully!")
            print(f"\nSQL:\n{result['sql']}")
            print(f"\nExplanation: {result['explanation']}")
            print(f"Confidence: {result['confidence']}")
        else:
            print(f"\n✗ Error: {result['error']}")

    except ValueError as e:
        print(f"\n✗ Error: {e}")
        print("\nPlease set ANTHROPIC_API_KEY environment variable")
