"""
AI Analyst Agent - Autonomous data analysis with multiple queries and visualizations

This agent can:
- Break down complex questions into multiple SQL queries
- Execute queries automatically
- Generate visualizations automatically
- Provide comprehensive analysis
- Format output for presentations
"""

import json
from typing import Dict, Any, List, Callable
from ai_query_generator_bedrock import AIQueryGenerator
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


class AIAnalystAgent:
    """Autonomous AI analyst that handles complex data analysis"""

    def __init__(self, execute_query_fn: Callable = None):
        self.ai_generator = AIQueryGenerator()
        self.conversation_history = []
        self.execute_query = execute_query_fn

    def analyze(self, question: str, language: str = 'en') -> Dict[str, Any]:
        """
        Perform comprehensive analysis for a complex question

        Args:
            question: The user's question
            language: 'en' for English or 'zh' for Chinese

        Returns a complete analysis with:
        - Multiple queries and results
        - Automatic visualizations
        - Narrative insights
        - Presentation-ready format
        """

        # Auto-detect Chinese input
        if language == 'en' and any('\u4e00' <= c <= '\u9fff' for c in question):
            language = 'zh'

        # Step 1: Create analysis plan
        plan = self._create_analysis_plan(question, language)

        if not plan['success']:
            return plan

        # Step 2: Execute all queries automatically
        results = []
        for i, query_step in enumerate(plan['queries'], 1):
            print(f"\n{'='*80}")
            print(f"QUERY {i}: {query_step['title']}")
            print(f"{'='*80}")
            print(f"SQL:\n{query_step['sql']}\n")

            query_result = self.execute_query(query_step['sql']) if self.execute_query else {'success': False, 'error': 'Query execution not available'}

            print(f"✓ Rows returned: {query_result.get('row_count', 0)}")
            print(f"✓ Success: {query_result.get('success', False)}")
            if not query_result.get('success'):
                print(f"✗ Error: {query_result.get('error')}")
            print(f"{'='*80}\n")

            results.append({
                'title': query_step['title'],
                'sql': query_step['sql'],
                'data': query_result.get('data', []),
                'columns': query_result.get('columns', []),
                'row_count': query_result.get('row_count', 0),
                'execution_time': query_result.get('execution_time', 0),
                'success': query_result.get('success', False),
                'error': query_result.get('error'),
                'visualization': query_step.get('visualization')
            })

        # Step 3: Generate visualizations automatically
        visualizations = []
        print(f"\n{'='*80}")
        print(f"VISUALIZATION GENERATION")
        print(f"{'='*80}")
        for i, result in enumerate(results):
            print(f"Query {i+1} - {result['title']}:")
            print(f"  Success: {result['success']}")
            print(f"  Has data: {len(result.get('data', [])) > 0}")
            print(f"  Has viz config: {result.get('visualization') is not None}")
            print(f"  Viz config: {result.get('visualization')}")

            if result['success'] and result['data'] and result.get('visualization'):
                print(f"  → Creating visualization...")
                viz = self._create_visualization(
                    result['data'],
                    result['visualization'],
                    result['title']
                )
                if viz:
                    print(f"  → ✓ Visualization created: {viz.get('type')}")
                    visualizations.append(viz)
                else:
                    print(f"  → ✗ Visualization creation failed")
            else:
                print(f"  → Skipped (missing success/data/config)")

        print(f"\nTotal visualizations generated: {len(visualizations)}")
        print(f"{'='*80}\n")

        # Step 4: Generate comprehensive insights
        insights = self._generate_insights(question, results, language)

        # Step 5: Format for presentation
        formatted_output = self._format_for_presentation(
            question,
            plan['analysis_approach'],
            results,
            visualizations,
            insights
        )

        return {
            'success': True,
            'question': question,
            'analysis_approach': plan['analysis_approach'],
            'results': results,
            'visualizations': visualizations,
            'insights': insights,
            'formatted_output': formatted_output,
            'timestamp': pd.Timestamp.now().isoformat()
        }

    def _create_analysis_plan(self, question: str, language: str = 'en') -> Dict[str, Any]:
        """Create a multi-step analysis plan"""

        # Get database context for SQL generation
        db_context = self.ai_generator.context

        language_instruction = ""
        if language == 'zh':
            language_instruction = "\n\n**IMPORTANT: Respond in Chinese (中文). Use Chinese for 'analysis_approach', 'title', 'purpose', and chart 'title'. SQL queries remain in English.**\n"

        system_prompt = f"""You are a data analyst planning how to answer a complex business question.{language_instruction}

CRITICAL: You MUST return ONLY a valid JSON object. No thinking, no explanations, no markdown text before the JSON. Start your response with {{ and end with }}.

# Database Context
{db_context}

# PREFERRED TABLE: Use gbis.biz.ads_kpi_summary_daily for brand analysis
For any brand-level analysis (STAR, APAC, etc.), prefer using `gbis.biz.ads_kpi_summary_daily` with `WHERE brand = 'STAR'`.
This table has: risk_free_revenue, risk_revenue, front_end_ecost, trading_volume, gross_company_pnl, net_company_pnl, spread_revenue, commission_revenue, swaps_revenue, dividend_revenue, rollover_revenue, gross_deposit, net_deposit, withdrawal, tdau, mau, client_type, country, second_region_name, is_inst, date, date_mm, date_y, date_q
NDM (Net Deposit Margin) = net_deposit / gross_deposit  (a RATIO, NOT net_deposit alone!)
  When user says "NDM": use ROUND(SUM(net_deposit) / NULLIF(SUM(gross_deposit), 0), 4) AS NDM
NRFR = risk_free_revenue - front_end_ecost
eROI = risk_free_revenue / NULLIF(front_end_ecost, 0)

## CRITICAL: Brand Name Mapping (use EXACT database names!)
| User says | Database brand value |
|-----------|---------------------|
| STAR, StarTrader | `STAR` |
| VT, VT Markets | `VT` |
| PU, PU Prime | `PU` |
| MM, Moneta Markets | `MM` |
| UM, Ultima Markets | `UM` |
| APAC | `APAC` |
| GS | `GS` |
| VTJ | `VTJ` |
All brand values: APAC, BYBIT, GS, MM, PU, STAR, UM, VT, VTJ

## CRITICAL: Region Name Mapping
| User says | Database second_region_name |
|-----------|---------------------------|
| EU, Europe | `Europe` |
| Asia, APAC region | `Asia` |
| LATAM, Latin America | `LATAM` |
| MENA, Middle East | `MENA` |
Use exact values: `WHERE second_region_name = 'Europe'` (NOT 'EU'!)

## CRITICAL: All monetary values are in USD ($)
ALL data in the database is denominated in US Dollars (USD). NEVER use €, ¥, £ or any other currency symbol.
Always use $ or "USD" when referring to monetary amounts in insights, even when analyzing European or Asian regions.
Example: "$213M" or "USD 213M", NEVER "€213M"

## CRITICAL: Column Alias Rule (Databricks)
NEVER alias an aggregation with the same name as the source column! Databricks will throw an error.
- WRONG:  `SUM(net_deposit) AS net_deposit`  then using `net_deposit` again
- CORRECT: `SUM(net_deposit) AS total_net_deposit`
Always prefix aliases with `total_`, `avg_`, `sum_` etc. to avoid collision with source column names.
Example: `SUM(gross_deposit) AS total_gross_deposit, SUM(net_deposit) AS total_net_deposit, ROUND(SUM(net_deposit)/NULLIF(SUM(gross_deposit),0), 4) AS NDM`

# IMPORTANT SQL Guidelines

## Table Selection:
1. **Simple aggregations** (by country, client_type, date) → Use `gbis.biz.dashboard_star_sales_metrics_daily`
   - Date column: `date` (NOT report_date!)
   - Withdrawal: `withdrawal` column
   - NO crm_server_id filter needed - already STAR-only!

2. **User-level analysis** (new vs existing users by ftd_date) → Use SOURCE tables:
   - `platinum.gbis.dws_login_metrics_daily` (has user_id, date, withdraw, crm_server_id)
   - `platinum.gbis.dim_user_base_daily_snapshot` (has user_id, ftd_date, register_date, live_date, ftt_date, country, crm_server_id — NO snapshot_date column!)
   - Date column: `date` (NOT report_date!)
   - Withdrawal: `withdraw` column (different spelling!)
   - MUST filter: WHERE t.crm_server_id = 1010

3. **Symbol/instrument-level analysis** (concentration, top symbols by volume/revenue) → Use:
   - `gbis.biz.dws_txau_by_symbol_di` (Trading users by symbol/asset type)
   - Columns: date, brand, **symbol_asset_type** (NOT "symbol"!), user_count, trading_volume, spread_revenue, risk_free_revenue, risk_revenue
   - Filter by: WHERE brand = 'STAR'
   - Example: `SELECT symbol_asset_type, SUM(trading_volume), SUM(spread_revenue) FROM gbis.biz.dws_txau_by_symbol_di WHERE brand = 'STAR' GROUP BY symbol_asset_type`

## CRITICAL: Column Names by Table!
**Dashboard tables (gbis.biz.dashboard_star_sales_metrics_daily):**
- Date: `date` (NOT report_date!)
- Withdrawal: `withdrawal`
- Deposits: `gross_deposit`, `net_deposit` (NO column named "deposit"!)
- Revenue columns: `risk_revenue`, `risk_free_revenue`, `gross_company_pnl`, `net_company_pnl`
- Revenue components: `spread_revenue`, `commission_revenue`, `swaps_revenue` (plural!), `dividend_revenue`, `rollover_revenue`
- Rebates: `ib_rebate`, `cpa_rebate`
- NO `crm_server_id` column - already pre-filtered for STAR!

**Source tables (platinum.gbis.dws_login_metrics_daily):**
- Date: `date` (NOT report_date!)
- Withdrawal: `withdraw`
- Deposits: `gross_deposit`, `net_deposit` (NO column named "deposit"!)
- HAS `crm_server_id` - filter by = 1010 for STAR!

**CRITICAL Column Name Corrections:**
- It's `swaps_revenue` (plural with 's'), NOT `swap_revenue`!
- NEVER use "deposit" alone - always specify `gross_deposit` or `net_deposit`!

## Business Formulas:
**Risk-Free Revenue = spread_revenue + dividend_revenue + rollover_revenue + commission_revenue + swaps_revenue**
**Net Risk-Free Revenue = risk_free_revenue - (ib_rebate + cpa_rebate)**

## Semantic Understanding (User Language → Column Names):
**Withdrawal terminology:**
- Users say "withdraw" or "withdrawal" → Both mean the same thing:
  - In `gbis.biz.dashboard_star_sales_metrics_daily` → use `withdrawal`
  - In `platinum.gbis.dws_login_metrics_daily` → use `withdraw`

**Deposit terminology (CRITICAL - two different metrics!):**
- Users say "gross deposit" → use `gross_deposit` column
- Users say "net deposit" → use `net_deposit` column
- Users say "deposit" alone → use `gross_deposit` (default to gross)
- NEVER use just "deposit" as column name - it doesn't exist!

**Date/Time terminology:**
- "ftd time" → use `ftd_date` column
- "ftt time" → use `ftt_date` column
- "register time" → use `register_date`

## Key Rules:
- Withdrawals are NEGATIVE values - use ABS() to show positive amounts
- For STAR brand: filter by crm_server_id = 1010
- Always: WHERE country IS NOT NULL AND country != 'Others'

## CRITICAL: Databricks SQL Date Function Syntax
**Date Arithmetic - Use DATE_SUB or DATE_ADD (NOT DATEADD!):**
```sql
-- CORRECT (Databricks/Spark SQL):
DATE_SUB(CURRENT_DATE(), 30)              -- 30 days ago
DATE_ADD(CURRENT_DATE(), 7)               -- 7 days from now
DATE_TRUNC('MONTH', date)                 -- First day of month

-- WRONG (don't use these):
DATEADD('month', -6, CURRENT_DATE)        -- Error: 'month' is a string
DATEADD(MONTH, -6, CURRENT_DATE)          -- Function not recognized
CURDATE()                                 -- Use CURRENT_DATE() instead
```

**For month/year arithmetic, use ADD_MONTHS (recommended):**
```sql
-- Subtract months:
ADD_MONTHS(CURRENT_DATE(), -6)            -- 6 months ago
ADD_MONTHS(CURRENT_DATE(), -12)           -- 12 months ago (1 year)
ADD_MONTHS(CURRENT_DATE(), -24)           -- 24 months ago (2 years)

-- Subtract days:
DATE_SUB(CURRENT_DATE(), 30)              -- 30 days ago
DATE_SUB(CURRENT_DATE(), 365)             -- 365 days ago

-- WRONG - DO NOT USE:
DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH)  -- Error in Databricks!
INTERVAL -1 YEAR                            -- Error in Databricks!
DATE_ADD(date, INTERVAL -1 YEAR)            -- Error in Databricks!
```

**Date truncation (CRITICAL - unit must be QUOTED!):**
```sql
-- CORRECT:
DATE_TRUNC('MONTH', CURRENT_DATE())       -- First day of current month
DATE_TRUNC('QUARTER', date)               -- First day of quarter
DATE_TRUNC('YEAR', date)                  -- First day of year
DATE_TRUNC('WEEK', date)                  -- First day of week

-- WRONG:
DATE_TRUNC(MONTH, date)                   -- Error: MONTH must be quoted!
DATE_TRUNC(YEAR, date)                    -- Error: YEAR must be quoted!
```

## New User Analysis (REQUIRES user_id):
**Must query platinum.gbis.dws_login_metrics_daily and JOIN with dim_user_base_daily_snapshot:**
```sql
FROM platinum.gbis.dws_login_metrics_daily t
LEFT JOIN platinum.gbis.dim_user_base_daily_snapshot u
    ON t.user_id = u.user_id AND t.crm_server_id = u.crm_server_id
WHERE t.crm_server_id = 1010
```
Then use: CASE WHEN u.ftd_date BETWEEN [start] AND [end] THEN 'New User' ELSE 'Existing User' END

Break down the question into 2-5 SQL queries that provide different perspectives.

Return ONLY a JSON object (no markdown, no code blocks, no explanations):
{{
    "analysis_approach": "Brief description of your approach",
    "queries": [
        {{
            "step": 1,
            "title": "Short title",
            "purpose": "Why this query",
            "sql": "The complete SQL query using proper table names and syntax",
            "visualization": {{
                "type": "bar|line|pie|table|scatter",
                "x": "column_name",
                "y": "column_name",
                "color": "grouping_column (optional, for multi-category data)",
                "title": "Chart title"
            }}
        }}
    ],
    "key_insights_to_look_for": ["insight 1", "insight 2"]
}}

## Chart Type Selection Rules:
**BAR charts:** Weekly/monthly aggregations, categorical comparisons
  - If query groups by category (country, client_type): ADD "color" field
  - Example: {{"type": "bar", "x": "week_start", "y": "withdrawal", "color": "country"}}

**LINE charts:** Daily time series, continuous trends
  - Can use "color" for multiple lines by category
  - Example: {{"type": "line", "x": "date", "y": "withdrawal", "color": "client_type"}}

Create queries that provide:
- Trend analysis over time (daily/weekly aggregation)
- Breakdown by key dimensions (country, client_type, etc.)
- Top/bottom performers
- Comparative analysis

CRITICAL: When query has GROUP BY with categories (country, client_type, user_segment),
ALWAYS include "color" field in visualization to show different groups with different colors."""

        try:
            print(f"\n{'#'*80}")
            print(f"CREATING ANALYSIS PLAN FOR: {question}")
            print(f"{'#'*80}\n")

            response = self.ai_generator._call_llm(
                system_prompt,
                [{"role": "user", "content": f"Question: {question}\n\nCreate an analysis plan with multiple SQL queries. Return ONLY valid JSON."}],
                max_tokens=4000
            )

            print(f"AI Response Length: {len(response)} chars")
            print(f"First 500 chars: {response[:500]}\n")

            # Parse JSON with robust error handling
            plan = self._extract_plan_json(response)

            if plan and 'queries' in plan and plan['queries']:
                # Validate each query has actual SQL
                valid_queries = []
                for q in plan['queries']:
                    sql = q.get('sql', '').strip()
                    if self._is_valid_sql(sql):
                        valid_queries.append(q)
                    else:
                        print(f"✗ Skipping invalid SQL in step '{q.get('title', '?')}': {sql[:100]}...")

                if valid_queries:
                    plan['queries'] = valid_queries
                    print(f"\n✓ JSON parsed successfully")
                    print(f"✓ Number of valid queries: {len(valid_queries)}")
                    if valid_queries[0].get('visualization'):
                        print(f"✓ First viz config: {valid_queries[0]['visualization']}")

                    return {
                        'success': True,
                        **plan
                    }

            # Fallback: try simple query generation
            print(f"Attempting fallback to simple query generation...")
            simple_result = self.ai_generator.generate_query(question)

            if simple_result['success'] and self._is_valid_sql(simple_result.get('sql', '')):
                return {
                    'success': True,
                    'analysis_approach': 'Single query analysis',
                    'queries': [
                        {
                            'step': 1,
                            'title': 'Analysis Query',
                            'purpose': simple_result.get('explanation', 'Address the user question'),
                            'sql': simple_result['sql'],
                            'visualization': {
                                'type': simple_result.get('suggested_chart', 'table'),
                                'x': simple_result.get('x_column'),
                                'y': simple_result.get('y_column'),
                                'title': 'Results'
                            }
                        }
                    ],
                    'key_insights_to_look_for': ['Trends', 'Patterns', 'Anomalies']
                }
            else:
                return {
                    'success': False,
                    'error': 'Analysis planning failed: AI did not return valid SQL queries. Please try rephrasing your question.'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Analysis planning failed: {str(e)}'
            }

    def _extract_plan_json(self, response: str) -> Dict:
        """Extract JSON plan from AI response, handling various formats"""
        import re

        # Strategy 1: Try to find ```json ... ``` code block
        json_block_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', response)
        if json_block_match:
            try:
                plan = json.loads(json_block_match.group(1))
                print("✓ Extracted JSON from code block (object)")
                return plan
            except json.JSONDecodeError:
                pass

        # Strategy 2: Try to find ```json [...] ``` array in code block
        json_array_block = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', response)
        if json_array_block:
            try:
                queries = json.loads(json_array_block.group(1))
                if isinstance(queries, list) and len(queries) > 0:
                    print(f"✓ Extracted JSON array from code block ({len(queries)} queries)")
                    return {
                        'analysis_approach': 'Multi-dimensional analysis',
                        'queries': [
                            {
                                'step': i + 1,
                                'title': q.get('title', q.get('explanation', f'Query {i+1}')),
                                'purpose': q.get('explanation', q.get('purpose', '')),
                                'sql': q.get('sql', ''),
                                'visualization': q.get('visualization', {
                                    'type': q.get('suggested_chart', 'table'),
                                    'x': q.get('x_column'),
                                    'y': q.get('y_column'),
                                    'title': q.get('title', f'Chart {i+1}')
                                })
                            }
                            for i, q in enumerate(queries)
                        ],
                        'key_insights_to_look_for': ['Trends', 'Patterns', 'Anomalies']
                    }
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find first { to last } (original approach)
        if '{' in response and '}' in response:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            json_str = response[json_start:json_end]
            try:
                plan = json.loads(json_str)
                print("✓ Extracted JSON from raw response (object)")
                return plan
            except json.JSONDecodeError:
                pass

        # Strategy 4: Find [ to ] for arrays not in code blocks
        if '[' in response and ']' in response:
            arr_start = response.find('[')
            arr_end = response.rfind(']') + 1
            arr_str = response[arr_start:arr_end]
            try:
                queries = json.loads(arr_str)
                if isinstance(queries, list) and len(queries) > 0 and isinstance(queries[0], dict):
                    print(f"✓ Extracted JSON array from raw response ({len(queries)} queries)")
                    return {
                        'analysis_approach': 'Multi-dimensional analysis',
                        'queries': [
                            {
                                'step': i + 1,
                                'title': q.get('title', q.get('explanation', f'Query {i+1}')),
                                'purpose': q.get('explanation', q.get('purpose', '')),
                                'sql': q.get('sql', ''),
                                'visualization': q.get('visualization', {
                                    'type': q.get('suggested_chart', 'table'),
                                    'x': q.get('x_column'),
                                    'y': q.get('y_column'),
                                    'title': q.get('title', f'Chart {i+1}')
                                })
                            }
                            for i, q in enumerate(queries)
                        ],
                        'key_insights_to_look_for': ['Trends', 'Patterns', 'Anomalies']
                    }
            except json.JSONDecodeError:
                pass

        print(f"✗ Failed to extract JSON from response (length: {len(response)})")
        print(f"First 300 chars: {response[:300]}")
        return None

    def _is_valid_sql(self, sql: str) -> bool:
        """Check if a string looks like valid SQL (not AI thinking text)"""
        if not sql or len(sql.strip()) < 10:
            return False
        sql_upper = sql.strip().upper()
        valid_starts = ('SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'SHOW', 'DESCRIBE', 'EXPLAIN')
        return sql_upper.startswith(valid_starts)

    def _create_visualization(self, data: List[Dict], viz_config: Dict, title: str) -> Dict:
        """Create a visualization from data"""

        if not data:
            return None

        df = pd.DataFrame(data)
        viz_type = viz_config.get('type', 'table')

        try:
            if viz_type == 'bar':
                # Support color dimension for grouped/stacked bars
                color = viz_config.get('color')
                fig = px.bar(
                    df,
                    x=viz_config.get('x'),
                    y=viz_config.get('y'),
                    color=color,  # For grouped/stacked bars
                    title=viz_config.get('title', title),
                    template='plotly_white',
                    barmode='group' if color else 'relative'  # group or stack
                )
            elif viz_type == 'line':
                # Support color dimension for multiple lines
                color = viz_config.get('color')
                fig = px.line(
                    df,
                    x=viz_config.get('x'),
                    y=viz_config.get('y'),
                    color=color,  # For multiple lines by category
                    title=viz_config.get('title', title),
                    template='plotly_white',
                    markers=True  # Add markers for better visibility
                )
            elif viz_type == 'pie':
                fig = px.pie(
                    df,
                    names=viz_config.get('x'),
                    values=viz_config.get('y'),
                    title=viz_config.get('title', title),
                    template='plotly_white'
                )
            elif viz_type == 'scatter':
                fig = px.scatter(
                    df,
                    x=viz_config.get('x'),
                    y=viz_config.get('y'),
                    title=viz_config.get('title', title),
                    template='plotly_white'
                )
            elif viz_type == 'heatmap':
                # Pivot data for heatmap
                pivot_df = df.pivot_table(
                    index=viz_config.get('x'),
                    columns=viz_config.get('y'),
                    values=df.columns[-1],
                    aggfunc='sum'
                )
                fig = px.imshow(
                    pivot_df,
                    title=viz_config.get('title', title),
                    template='plotly_white'
                )
            else:  # table
                return {
                    'type': 'table',
                    'data': data[:10],  # First 10 rows for preview
                    'title': title
                }

            # Enhance layout for presentation
            fig.update_layout(
                font=dict(size=12),
                title_font_size=16,
                showlegend=True,
                height=400
            )

            return {
                'type': viz_type,
                'chart': json.loads(fig.to_json()),
                'title': title
            }

        except Exception as e:
            print(f"Visualization error: {e}")
            return None

    def _generate_insights(self, question: str, results: List[Dict], language: str = 'en') -> Dict:
        """Generate comprehensive insights from all results"""

        # Prepare summary of results
        results_summary = []
        for r in results:
            if r['success']:
                results_summary.append({
                    'title': r['title'],
                    'row_count': r['row_count'],
                    'sample_data': r['data'][:5] if r['data'] else []
                })

        language_instruction = ""
        if language == 'zh':
            language_instruction = "\n\n**CRITICAL: Write your entire response in Chinese (中文). Use Chinese for all text, headings, and explanations.**\n"

        system_prompt = f"""You are a senior data analyst presenting findings to executives.{language_instruction}

Analyze the query results and provide:

1. **Executive Summary** (2-3 sentences) - Key findings at a glance
2. **Key Insights** (3-5 bullet points) - Most important discoveries
3. **Trends & Patterns** - What the data reveals
4. **Recommendations** (2-3 points) - Actionable next steps
5. **Caveats** - Any limitations or considerations

Format your response in clear sections with markdown formatting.
Use specific numbers from the data to support your insights.
Be concise and focus on business impact."""

        user_prompt = f"""Original Question: {question}

Query Results Summary:
{json.dumps(results_summary, indent=2, default=str)}

Provide comprehensive insights for a presentation."""

        try:
            insights = self.ai_generator._call_llm(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
                max_tokens=2000
            )

            return {
                'success': True,
                'content': insights
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def translate_text(self, insights: str, analysis_approach: str, target_language: str) -> Dict:
        """Translate insights and analysis approach to target language"""

        if target_language == 'zh':
            language_name = "Chinese (中文)"
            instruction = "Translate the following business analysis text to Chinese. Maintain all markdown formatting, numbers, and structure."
        else:
            language_name = "English"
            instruction = "Translate the following business analysis text to English. Maintain all markdown formatting, numbers, and structure."

        system_prompt = f"""{instruction}

Keep:
- All numerical values unchanged
- All markdown formatting (**, ##, lists, etc.)
- Professional business terminology
- Clear and concise language

Translate the insights and analysis approach provided by the user."""

        user_prompt = f"""# Analysis Approach
{analysis_approach}

# Insights
{insights}"""

        try:
            translated = self.ai_generator._call_llm(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
                max_tokens=3000
            )

            # Parse out analysis_approach and insights from response
            # Simple split by section headers
            parts = translated.split('# Insights', 1)
            if len(parts) == 2:
                translated_approach = parts[0].replace('# Analysis Approach', '').strip()
                translated_insights = parts[1].strip()
            else:
                # Fallback: use entire translation as insights
                translated_approach = analysis_approach
                translated_insights = translated

            return {
                'success': True,
                'analysis_approach': translated_approach,
                'insights': translated_insights
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _format_for_presentation(
        self,
        question: str,
        approach: str,
        results: List[Dict],
        visualizations: List[Dict],
        insights: Dict
    ) -> Dict:
        """Format everything into presentation-ready output"""

        return {
            'title': question,
            'approach': approach,
            'sections': [
                {
                    'type': 'executive_summary',
                    'content': insights.get('content', 'Analysis in progress...')
                },
                {
                    'type': 'data_analysis',
                    'results': results
                },
                {
                    'type': 'visualizations',
                    'charts': visualizations
                }
            ],
            'metadata': {
                'total_queries': len(results),
                'successful_queries': sum(1 for r in results if r['success']),
                'total_rows': sum(r['row_count'] for r in results if r['success']),
                'visualizations': len(visualizations)
            }
        }


def create_agent() -> AIAnalystAgent:
    """Create an AI Analyst Agent instance"""
    return AIAnalystAgent()


if __name__ == "__main__":
    # Test the agent
    agent = AIAnalystAgent()

    result = agent.analyze(
        "What are the top performing countries for STAR brand? Show me FTD, deposits, and trading volume trends."
    )

    if result['success']:
        print("✅ Analysis Complete!")
        print(f"Executed {len(result['results'])} queries")
        print(f"Generated {len(result['visualizations'])} visualizations")
    else:
        print(f"❌ Error: {result.get('error')}")
