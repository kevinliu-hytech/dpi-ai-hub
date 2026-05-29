"""
AI-Powered Query Generator with AWS Bedrock Support

This module supports both:
1. Direct Anthropic API
2. AWS Bedrock with Claude models
"""

import os
import json
from typing import Dict, Any, Optional
from query_loader import QueryKnowledgeBase


class AIQueryGenerator:
    """Generate SQL queries from natural language using Claude via Anthropic API or AWS Bedrock"""

    def __init__(self, provider: Optional[str] = None, **kwargs):
        """
        Initialize the AI Query Generator

        Args:
            provider: 'anthropic' or 'bedrock'. If not provided, uses AI_PROVIDER env var
            **kwargs: Additional configuration (api_key for Anthropic, region for Bedrock, etc.)
        """
        self.provider = provider or os.getenv('AI_PROVIDER', 'bedrock').lower()
        self.kb = QueryKnowledgeBase()
        self.context = self.kb.get_context_for_ai()

        if self.provider == 'anthropic':
            self._init_anthropic(**kwargs)
        elif self.provider == 'bedrock':
            self._init_bedrock(**kwargs)
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}. Use 'anthropic' or 'bedrock'")

    def _init_anthropic(self, **kwargs):
        """Initialize Anthropic API client"""
        from anthropic import Anthropic

        api_key = kwargs.get('api_key') or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found")

        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        print("✓ Using Anthropic API")

    def _init_bedrock(self, **kwargs):
        """Initialize AWS Bedrock client"""
        import boto3

        # Get AWS credentials
        region = kwargs.get('region') or os.getenv('AWS_REGION', 'us-east-1')
        aws_access_key = kwargs.get('aws_access_key_id') or os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = kwargs.get('aws_secret_access_key') or os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_profile = kwargs.get('aws_profile') or os.getenv('AWS_PROFILE')

        # Create boto3 session
        session_kwargs = {'region_name': region}

        if aws_profile:
            # Use named profile
            session_kwargs['profile_name'] = aws_profile
            print(f"✓ Using AWS profile: {aws_profile}")
        elif aws_access_key and aws_secret_key:
            # Use explicit credentials
            session_kwargs['aws_access_key_id'] = aws_access_key
            session_kwargs['aws_secret_access_key'] = aws_secret_key
            print(f"✓ Using AWS credentials (access key)")
        else:
            # Use default credentials (IAM role, instance profile, etc.)
            print(f"✓ Using AWS default credentials (IAM role/instance profile)")

        try:
            session = boto3.Session(**session_kwargs)
            self.client = session.client('bedrock-runtime', region_name=region)

            # Model ID for Claude on Bedrock
            self.model = kwargs.get('model_id') or os.getenv(
                'BEDROCK_MODEL_ID',
                'anthropic.claude-sonnet-4-20250514-v1:0'
            )

            self.region = region
            print(f"✓ Using AWS Bedrock in {region}")
            print(f"✓ Model: {self.model}")

        except Exception as e:
            raise ValueError(f"Failed to initialize AWS Bedrock: {str(e)}")

    def _call_anthropic(self, system_prompt: str, messages: list, max_tokens: int = 2000) -> str:
        """Call Anthropic API"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages
        )
        return response.content[0].text

    def _call_bedrock(self, system_prompt: str, messages: list, max_tokens: int = 2000) -> str:
        """Call AWS Bedrock with Claude model"""
        # Format request for Bedrock's Claude API
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages
        }

        # Call Bedrock
        response = self.client.invoke_model(
            modelId=self.model,
            body=json.dumps(request_body)
        )

        # Parse response
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    def _call_llm(self, system_prompt: str, messages: list, max_tokens: int = 2000) -> str:
        """Call the configured LLM provider"""
        if self.provider == 'anthropic':
            return self._call_anthropic(system_prompt, messages, max_tokens)
        elif self.provider == 'bedrock':
            return self._call_bedrock(system_prompt, messages, max_tokens)

    def _preprocess_metric_names(self, text: str) -> str:
        """
        Preprocess user input to replace metric names with exact column names
        This ensures exact matching before LLM interpretation
        """
        # Define exact mappings (case-insensitive)
        metric_mappings = {
            # NDM = Net Deposit Margin = net_deposit / gross_deposit (ratio, NOT net_deposit alone!)
            'ndm': 'NDM_RATIO',  # Flag for special handling

            # Revenue columns
            'risk free revenue': 'risk_free_revenue',
            'risk-free revenue': 'risk_free_revenue',
            'riskfree revenue': 'risk_free_revenue',
            'risk free': 'risk_free_revenue',
            'risk revenue': 'risk_revenue',

            # Deposit columns - CRITICAL: never use "deposit" alone!
            'gross deposit': 'gross_deposit',
            'net deposit': 'net_deposit',
            'total deposit': 'gross_deposit',  # Default to gross

            # Withdrawal columns
            'total withdrawal': 'withdrawal',  # or 'withdraw' depending on table

            # Other financial columns
            'trading volume': 'trading_volume',
            'gross company pnl': 'gross_company_pnl',
            'net company pnl': 'net_company_pnl',
            'company pnl': 'gross_company_pnl',

            # Date columns - users say "time", database uses "date"
            'ftd time': 'ftd_date',
            'ftt time': 'ftt_date',
            'register time': 'register_date',
            'live time': 'live_date',

            # Amount columns
            'ftd amount': 'ftd_amount',
            'ftt amount': 'ftt_amount',

            # Revenue component columns
            'swap revenue': 'swaps_revenue',  # Important: plural!
            'swaps revenue': 'swaps_revenue',
            'spread revenue': 'spread_revenue',
            'commission revenue': 'commission_revenue',
            'dividend revenue': 'dividend_revenue',
            'rollover revenue': 'rollover_revenue',

            # Rebate columns
            'ib rebate': 'ib_rebate',
            'cpa rebate': 'cpa_rebate',
        }

        # Sort by length (longest first) to match longer phrases first
        sorted_mappings = sorted(metric_mappings.items(), key=lambda x: len(x[0]), reverse=True)

        processed_text = text.lower()
        replacements = []

        # Find all matches
        for phrase, column_name in sorted_mappings:
            if phrase in processed_text:
                replacements.append((phrase, column_name))

        # Apply replacements to original text (preserve case for non-metric parts)
        result = text
        for phrase, column_name in replacements:
            # Case-insensitive replacement
            import re
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            result = pattern.sub(column_name, result)

        return result

    def generate_query(self, natural_language: str, conversation_history: list = None) -> Dict[str, Any]:
        """
        Convert natural language to SQL query

        Args:
            natural_language: The user's question in plain English
            conversation_history: Previous conversation messages for context

        Returns:
            Dict with 'sql', 'explanation', and 'confidence' keys
        """

        # Preprocess to replace metric names with exact column names
        preprocessed_input = self._preprocess_metric_names(natural_language)

        # If preprocessing changed the input, use the preprocessed version
        query_input = preprocessed_input if preprocessed_input != natural_language else natural_language

        # Auto-detect Chinese: if input contains Chinese characters, respond in Chinese
        is_chinese = any('\u4e00' <= c <= '\u9fff' for c in natural_language)
        language_instruction = "\n\nIMPORTANT: The user wrote in Chinese. Write the 'explanation' field in Chinese (中文). SQL remains in English.\n" if is_chinese else ""

        system_prompt = f"""You are an expert SQL query generator for a business intelligence system using Databricks SQL.{language_instruction}

# Database Context
{self.context}

# CRITICAL: STAR Brand Data Model Understanding

## Table Selection:
**For WITHDRAWAL, DEPOSIT, TRADING metrics (simple aggregations):**
- USE: `gbis.biz.dashboard_star_sales_metrics_daily`
- Date column: `date` (NOT report_date!)
- Withdrawal column: `withdrawal`
- DO NOT filter by crm_server_id - this table is already STAR-only!
- Example: `SELECT date, ABS(SUM(withdrawal)) FROM gbis.biz.dashboard_star_sales_metrics_daily WHERE date BETWEEN...`

**For USER EVENT metrics (register, live, FTD, FTT):**
- USE: `gbis.biz.dashboard_star_fact_daily_kpi`

**For CPA metrics:** `gbis.biz.dashboard_star_cpa_metrics_daily`
**For IB metrics:** `gbis.biz.dashboard_star_ib_metrics_daily`

**For SYMBOL/INSTRUMENT-LEVEL ANALYSIS (Universal Table):**
- USE: `gbis.biz.dws_txau_by_symbol_di`
- Columns: date, brand, **symbol_asset_type** (NOT "symbol"!), user_count, trading_volume, spread_revenue, risk_free_revenue, risk_revenue, period, client_type, second_region_name, country, is_inst
- Filter by: WHERE brand = 'STAR'
- This shows which symbols/instruments generate the most trading activity and revenue
- Example: `SELECT symbol_asset_type, SUM(trading_volume), SUM(spread_revenue) FROM gbis.biz.dws_txau_by_symbol_di WHERE brand = 'STAR' AND date >= DATE_SUB(CURRENT_DATE(), 90) GROUP BY symbol_asset_type ORDER BY SUM(trading_volume) DESC`

**For USER-LEVEL ANALYSIS (need user_id, ftd_date):**
- USE: `platinum.gbis.dws_login_metrics_daily` (has user_id, date, withdraw, crm_server_id)
- JOIN WITH: `platinum.gbis.dim_user_base_daily_snapshot` (has user_id, ftd_date, crm_server_id)
- Date column: `date` (NOT report_date!)
- Withdrawal column: `withdraw` (NOT withdrawal!)
- MUST filter: WHERE t.crm_server_id = 1010 (for STAR brand)
- Example: `SELECT t.date, u.ftd_date FROM platinum.gbis.dws_login_metrics_daily t JOIN platinum.gbis.dim_user_base_daily_snapshot u ON t.user_id = u.user_id WHERE t.crm_server_id = 1010`

## CRITICAL: Understanding Table Architecture for User-Level Analysis

**Two types of tables available:**

### 1. Aggregated Dashboard Tables (NO user_id - pre-aggregated)
- `gbis.biz.dashboard_star_sales_metrics_daily`
- `gbis.biz.dashboard_star_fact_daily_kpi`
- Use these for: Country/client_type/date aggregations WITHOUT needing user-level data

### 2. Source Tables (HAS user_id - granular data)
- **`platinum.gbis.dws_login_metrics_daily`** - Daily trading metrics per user
  - Columns: user_id, date, withdraw, gross_deposit, net_deposit, trading_volume, revenue columns
  - Use for: User-level analysis, withdrawal behavior by user

- **`platinum.gbis.dim_user_base_daily_snapshot`** - User dimension
  - Columns: user_id, ftd_date, register_date, country, crm_server_id
  - Use for: FTD date, user registration info, user country

- **`platinum.gbis.dim_login_ownership_monthly`** - Sales/ownership attribution
  - Use for: Sales team, client_type, account_type attribution

## New User vs Existing User Analysis - CORRECT APPROACH

**When you need to segment by ftd_date (new vs existing users), use SOURCE tables:**

```sql
-- Example: Withdrawal analysis by new vs existing users
SELECT
    t.date,
    u.country,
    lm.client_type,
    CASE
        WHEN u.ftd_date BETWEEN '2026-01-01' AND '2026-04-10' THEN 'New User'
        WHEN u.ftd_date < '2026-01-01' THEN 'Existing User'
        ELSE 'Unknown'
    END AS user_cohort,
    COUNT(DISTINCT t.user_id) as user_count,
    ABS(SUM(t.withdraw)) as total_withdrawal
FROM platinum.gbis.dws_login_metrics_daily t
LEFT JOIN platinum.gbis.dim_user_base_daily_snapshot u
    ON t.user_id = u.user_id
    AND t.crm_server_id = u.crm_server_id
LEFT JOIN platinum.gbis.dim_login_ownership_monthly lm
    ON t.login = lm.login
    AND t.server_id = lm.server_id
    AND date_format(t.date, 'yyyy-MM') = lm.month
WHERE t.date BETWEEN '2026-01-01' AND '2026-04-10'
    AND t.crm_server_id = 1010  -- STAR brand
    AND lm.brand = 'STAR'
    AND u.ftd_date IS NOT NULL
GROUP BY t.date, u.country, lm.client_type, user_cohort
ORDER BY t.date DESC
```

**Key points:**
- Use `t.withdraw` column from dws_login_metrics_daily (note: withdrawals are negative)
- Join with dim_user_base_daily_snapshot to get ftd_date
- Filter by crm_server_id = 1010 for STAR brand
- Join with dim_login_ownership_monthly for client_type/sales attribution

## IMPORTANT Query Patterns (from ETL examples):

**For financial metrics (withdrawal, deposits), ALWAYS include:**
1. **Dimension filters** - The data is granular by sales/account/client:
   - Filter or group by: `country`, `account_type`, `client_type`, `sales_name`, `sales_org_name`

2. **Data quality filters**:
   - Exclude NULL countries: `WHERE country IS NOT NULL AND country != 'Others'`

3. **CRITICAL: Withdrawal Column Name Varies by Table!**
   - Dashboard tables: `gbis.biz.dashboard_star_sales_metrics_daily` → use `withdrawal` column
   - Source tables: `platinum.gbis.dws_login_metrics_daily` → use `withdraw` column
   - Same metric, different column names!

4. **CRITICAL: Withdrawal Value Handling**:
   - Withdrawals are stored as NEGATIVE values (accounting convention)
   - For "top countries by withdrawal", use: `ORDER BY total_withdrawal ASC` (most negative = highest withdrawal)
   - Or use `ABS(SUM(withdrawal))` or `ABS(SUM(withdraw))` to show as positive amounts
   - Do NOT use `HAVING total_withdrawal > 0` - this will return 0 rows!

3. **RLS awareness** - Data includes row-level security flags:
   - has_emma, has_harry, has_adam, etc. (don't filter by these unless asked)

4. **Account type distinctions**:
   - 'Retail', 'OZ', 'Hybrid', 'IB' - These are important dimensions
   - OZ accounts might have different logic

**Example pattern for top countries by withdrawal:**
```sql
SELECT
    country,
    ABS(SUM(withdrawal)) as total_withdrawal,  -- Use ABS() since withdrawals are negative
    COUNT(DISTINCT sales_name) as sales_count
FROM gbis.biz.dashboard_star_sales_metrics_daily
WHERE date >= DATE_SUB(CURRENT_DATE(), 7)
    AND country IS NOT NULL
    AND country != 'Others'
    AND withdrawal != 0  -- Exclude rows with no withdrawal activity
GROUP BY country
ORDER BY total_withdrawal DESC  -- Now DESC works correctly
LIMIT 5
```

## Column Names by Table (CRITICAL - use EXACT names!):

**Aggregated Tables (gbis.biz.dashboard_star_sales_metrics_daily):**
- Date column: `date` (NOT "report_date"!)
- Withdrawal column: `withdrawal` (NOT "withdraw"!)
- Deposit columns: `gross_deposit`, `net_deposit` (NO column named just "deposit"!)
- NO `crm_server_id` column - these tables are already STAR-only, pre-filtered!
- NO `user_id` column - pre-aggregated!
- Has: `country`, `client_type`, `account_type`, `sales_name`, `sales_org_name`
- Has: `trading_volume`, `ftd`, `ftd_amount`, `ftt`, `ftt_amount`
- Has: `risk_revenue`, `risk_free_revenue`, `gross_company_pnl`, `net_company_pnl`
- Has: `spread_revenue`, `commission_revenue`, `swaps_revenue` (note: plural!), `dividend_revenue`, `rollover_revenue`
- Has: `ib_rebate`, `cpa_rebate`

**Source Tables (platinum.gbis.dws_login_metrics_daily):**
- Date column: `date` (NOT "report_date"!)
- Withdrawal column: `withdraw` (NOT "withdrawal"!)
- Deposit columns: `gross_deposit`, `net_deposit` (NO column named just "deposit"!)
- HAS `crm_server_id` - filter by crm_server_id = 1010 for STAR
- HAS `user_id` - can join with user dimension
- Has: `trading_volume`, `login`, `server_id`
- Has: Revenue columns (`risk_revenue`, `risk_free_revenue`, etc.)

**CRITICAL: Never abbreviate column names!**
- User says "gross deposit" → Use `gross_deposit` (NOT "deposit"!)
- User says "net deposit" → Use `net_deposit` (NOT "deposit"!)
- User says "deposit" alone → Ask which one, or use `gross_deposit` by default
- There is NO column named just "deposit" - always specify gross or net!

**User Dimension (platinum.gbis.dim_user_base_daily_snapshot):**
- `user_id`, `ftd_date`, `register_date`, `live_date`, `ftt_date`, `live_kyc_date`
- `country`, `crm_server_id`
- **NO `snapshot_date` column!** This table has NO date/timestamp column for filtering by date range. Use `ftd_date` or `register_date` for date-based user filtering.

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

## CRITICAL: Column Alias Rule (Databricks)
NEVER alias an aggregation with the same name as the source column! Databricks throws MISSING_ATTRIBUTES error.
- WRONG:  `SUM(net_deposit) AS net_deposit`
- CORRECT: `SUM(net_deposit) AS total_net_deposit`
Always prefix aliases: `total_`, `avg_`, `sum_` to avoid collision with source column names.

## CRITICAL: Revenue Column Name (Plural!)
**IMPORTANT:** The column is `swaps_revenue` (plural with 's'), NOT `swap_revenue`!
- User says "swap revenue" → Use `swaps_revenue` column (with 's')
- User says "swaps revenue" → Use `swaps_revenue` column

## Business Formulas (Revenue Breakdown):
**Risk-Free Revenue Components:**
```
risk_free_revenue = spread_revenue + dividend_revenue + rollover_revenue + commission_revenue + swaps_revenue
```

**Net Risk-Free Revenue (After Rebates):**
```
net_risk_free_revenue = risk_free_revenue - (ib_rebate + cpa_rebate)
```
OR calculate directly:
```
net_risk_free_revenue = (spread_revenue + dividend_revenue + rollover_revenue + commission_revenue + swaps_revenue) - (ib_rebate + cpa_rebate)
```

**Risk Revenue:**
- Market-driven revenue from risk exposure
- Should correlate with market volatility
- Compare with risk_free_revenue to understand revenue stability

## CRITICAL: Semantic Mappings (User Language → Database Terms)
When users say:
- "withdraw" or "withdrawal" → Use `withdrawal` for dashboard tables, `withdraw` for dws_login_metrics_daily
- "swap revenue" or "swaps revenue" → Use `swaps_revenue` (plural!)
- "ftd time" → Use `ftd_date` column
- "ftt time" → Use `ftt_date` column
- "register time" → Use `register_date`
- These are semantically equivalent in user questions but have specific column names in the database!

## CRITICAL: When you see column names in the user input, USE THEM EXACTLY
- If input contains `risk_free_revenue` → Use `risk_free_revenue` column
- If input contains `risk_revenue` → Use `risk_revenue` column
- If input contains `ftd_date` → Use `ftd_date` column
- If input contains column names with underscores, they are EXACT column names - use them as-is!

# Important Guidelines
1. Generate Databricks SQL (Spark SQL) compatible queries
2. Always use proper table names from the context above (format: catalog.schema.table)
3. For STAR brand queries, use tables in gbis.biz schema (e.g., gbis.biz.dashboard_star_fact_daily_kpi)
4. Include date filters when appropriate (data starts from 2025-01-01)
5. Use appropriate aggregations (SUM, COUNT, AVG) for metrics
6. Group by dimensions when aggregating
7. Order results by date DESC or by the main metric DESC
8. Add LIMIT clauses (default 100) unless specifically asked for all data
9. Use COALESCE for null handling when needed
10. Format currency and numbers appropriately
11. Column names are case-sensitive - use exact names as specified above

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

-- Add dates:
DATE_ADD(CURRENT_DATE(), 7)               -- 7 days from now

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

**Always use:**
- `CURRENT_DATE()` for today's date (NOT CURDATE() or NOW())
- `DATE_FORMAT(date, 'yyyy-MM')` for formatting dates
- `YEAR(date)`, `MONTH(date)`, `DAY(date)` for extracting date parts
- `DAYOFWEEK(date)` returns 1=Sunday, 2=Monday, ..., 7=Saturday
- `ADD_MONTHS(date, n)` for month/year arithmetic (NOT INTERVAL syntax!)

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
    "sql": "SELECT date, SUM(ftd) as total_ftd FROM gbis.biz.dashboard_star_fact_daily_kpi WHERE date >= DATE_SUB(CURRENT_DATE(), 30) GROUP BY date ORDER BY date DESC",
    "explanation": "Returns daily first-time deposits for the last 30 days",
    "confidence": "high",
    "suggested_chart": "line",
    "x_column": "date",
    "y_column": "total_ftd"
}}
"""

        messages = conversation_history or []
        messages.append({
            "role": "user",
            "content": query_input
        })

        try:
            content = self._call_llm(system_prompt, messages)

            # Parse JSON response
            result = None
            try:
                if '{' in content and '}' in content:
                    json_start = content.find('{')
                    json_end = content.rfind('}') + 1
                    json_str = content[json_start:json_end]
                    result = json.loads(json_str)
            except json.JSONDecodeError:
                pass

            # If JSON parsing failed, try to extract SQL from code blocks or raw text
            if result is None or not self._is_valid_sql(result.get('sql', '')):
                extracted_sql = self._extract_sql_from_text(content)
                if extracted_sql:
                    result = {
                        "sql": extracted_sql,
                        "explanation": "Generated SQL query",
                        "confidence": "medium",
                        "suggested_chart": None,
                        "x_column": None,
                        "y_column": None
                    }
                else:
                    return {
                        "success": False,
                        "error": "AI did not return valid SQL. Please try rephrasing."
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

    def _is_valid_sql(self, sql: str) -> bool:
        """Check if a string looks like valid SQL"""
        if not sql or len(sql.strip()) < 10:
            return False
        sql_upper = sql.strip().upper()
        valid_starts = ('SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'SHOW', 'DESCRIBE', 'EXPLAIN')
        return sql_upper.startswith(valid_starts)

    def _extract_sql_from_text(self, text: str) -> str:
        """Extract SQL from AI response that may contain thinking text or JSON"""
        import re

        # Try to find SQL in ```sql ... ``` code block
        sql_match = re.search(r'```sql\s*([\s\S]*?)```', text)
        if sql_match:
            sql = sql_match.group(1).strip()
            if self._is_valid_sql(sql):
                return sql

        # Try to extract sql field from JSON string
        sql_json_match = re.search(r'"sql"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if sql_json_match:
            sql = sql_json_match.group(1).replace('\\n', ' ').replace('\\"', '"').strip()
            if self._is_valid_sql(sql):
                return sql

        # Try to find a SELECT/WITH statement in the raw text
        for keyword in ['SELECT', 'WITH']:
            idx = text.upper().find(keyword)
            if idx >= 0:
                candidate = text[idx:]
                # Trim at common JSON/markdown boundaries
                for boundary in ['```', '",\n', '",\\n', '"\n', '"explanation"', '"confidence"']:
                    end = candidate.find(boundary)
                    if end > 0:
                        candidate = candidate[:end]
                        break
                candidate = candidate.strip().rstrip('",;').strip()
                if len(candidate) > 20 and self._is_valid_sql(candidate):
                    return candidate

        return None

    def analyze_data(self, query: str, data: list, question: str = None) -> Dict[str, Any]:
        """Analyze query results and provide insights"""

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
            analysis = self._call_llm(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
                max_tokens=1500
            )

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
        """Attempt to fix a failed query based on error message"""

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
            content = self._call_llm(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
                max_tokens=1500
            )

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


def create_generator(provider: Optional[str] = None, **kwargs) -> AIQueryGenerator:
    """Create an AI Query Generator instance"""
    return AIQueryGenerator(provider=provider, **kwargs)


if __name__ == "__main__":
    # Test the generator
    print("Testing AI Query Generator with AWS Bedrock...")

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

    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nPlease configure AWS credentials or set AI_PROVIDER=anthropic with ANTHROPIC_API_KEY")
