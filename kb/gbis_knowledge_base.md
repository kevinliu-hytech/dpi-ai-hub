# GBIS Business Intelligence Knowledge Base

This knowledge base contains all business logic, schema definitions, metric formulas, and SQL rules for the GBIS data platform. It is the single source of truth shared across all AI-powered products (Dashboard, Deep Insight, Exec Chatbot).

---

## 1. Business Context

GBIS (Global Broker Intelligence System) is a multi-brand online trading brokerage platform. All data is in USD.

### Brands
| Brand Name | Database Value | Aliases |
|-----------|---------------|---------|
| StarTrader | `STAR` | STAR, StarTrader |
| VT Markets | `VT` | VT |
| PU Prime | `PU` | PU |
| Moneta Markets | `MM` | MM |
| Ultima Markets | `UM` | UM |
| APAC | `APAC` | APAC |
| GS | `GS` | GS |
| VTJ | `VTJ` | VTJ |
| BYBIT | `BYBIT` | (excluded from most analysis) |

All brand values in database: `APAC, BYBIT, GS, MM, PU, STAR, UM, VT, VTJ`

Standard exclusion filter: `WHERE brand NOT IN ('Others', 'BYBIT')`

Brand combination rules:
- **KPI目标完成度相关查询**：APAC和VTJ必须合并计算（`CASE WHEN brand IN ('APAC','VTJ') THEN 'APAC + VTJ' ELSE brand END`），因为`dim_kpi_target`表中目标值存储为`brand = 'APAC + VTJ'`。回答中需标注"APAC含VTJ"。
- **其他非目标相关查询**：APAC和VTJ正常分开，各自独立展示。

### Regions
| User Says | Database `second_region_name` |
|-----------|-------------------------------|
| EU, Europe | `Europe` |
| Asia, APAC region | `Asia` |
| LATAM, Latin America | `LATAM` |
| MENA, Middle East | `MENA` |

All region values: `Asia, BYBIT, Europe, LATAM, MENA, Others`

### Client Types
- Retail, OZ, Hybrid, IB
- OZ accounts have different logic (no concept of active users)

---

## 2. Metric Definitions (Non-Negotiable Rules)

These are exact formulas. Any AI system using this KB MUST use these definitions verbatim.

### NDM (Net Deposit Margin)
```
NDM = (net_deposit + rt) / gross_deposit
```
- NDM is a RATIO, NOT an amount
- Column name varies by table:
  - `ads_kpi_summary_daily` → column is `rt`
  - `dashboard_star_sales_metrics_daily` → column is `rt_value`
- SQL (ads_kpi): `ROUND((SUM(net_deposit) + SUM(rt)) / NULLIF(SUM(gross_deposit), 0), 4) AS NDM`
- SQL (dashboard_star): `ROUND((SUM(net_deposit) + SUM(rt_value)) / NULLIF(SUM(gross_deposit), 0), 4) AS NDM`
- When user says "NDM", NEVER return just `net_deposit`

### NRFR (Net Risk-Free Revenue)
```
NRFR = risk_free_revenue - front_end_ecost_daily_report
```
- Uses `front_end_ecost_daily_report`

### RFR (Risk-Free Revenue)
```
RFR = risk_free_revenue
```

### Risk-Free Revenue Components
```
risk_free_revenue = spread_revenue + commission_revenue + swaps_revenue + dividend_revenue + rollover_revenue
```

### eROI (Efficiency ROI)
```
eROI = risk_free_revenue / NULLIF(front_end_ecost, 0)
```

### TDAU (Trading DAU)
- Active trading users per day
- Calculated as: users with `trading_volume - toc_trading_volume > 0`
- Variations: `tdau`, `tdau_wo_toc`, `tdau_fix`, `tdau_wo_toc_fix`

### Withdrawal Rules
- Withdrawals are stored as NEGATIVE values (accounting convention)
- Display as positive: use `ABS(SUM(withdrawal))`
- For "top by withdrawal": `ORDER BY total_withdrawal ASC` (most negative = highest) or use ABS()
- Never use `HAVING total_withdrawal > 0` (returns 0 rows)

### Date Type Flag
```sql
IF(DAYOFWEEK(date) BETWEEN 2 AND 6, 1, 0) AS date_type
```
Weekdays (Mon-Fri) = 1, Weekends = 0. Used for weekday-only analysis.

---

## 3. Table Architecture

### 3.1 Universal KPI Table (Primary - All Brands)

**`gbis.biz.ads_kpi_summary_daily`**

The go-to table for any brand-level analysis. Filter by `WHERE brand = 'STAR'`.

**Dimensions:**
- `date`, `date_mm` (month), `date_y` (year), `date_q` (quarter)
- `brand`, `client_type`, `country`, `second_region_name`, `is_inst`

**User & Activity Metrics:**
- `register_count`, `live_count`, `ftd_count`, `ftt_count`
- `tdau`, `tdau_wo_toc`, `tdau_fix`, `tdau_wo_toc_fix`
- `funding_dau`, `mau`

**Financial Metrics:**
- `gross_deposit`, `net_deposit`, `withdrawal`
- `trading_volume`, `trading_volume_wo_toc`
- `rt` (net deposit rate), `equity`, `equity_filtered`

**Revenue:**
- `spread_revenue`, `commission_revenue`, `swaps_revenue` (PLURAL!), `dividend_revenue`, `rollover_revenue`
- `risk_free_revenue`, `risk_revenue`

**PnL:**
- `net_company_pnl`, `gross_company_pnl`, `gross_client_pnl`

**Costs & Commissions:**
- `front_end_ecost`, `front_end_ecost_daily_report`
- `ib_rebate`, `cpa_commission`, `sales_commission`, `sales_commission_nd`
- `psp_charge`

**Aggregated (Monthly/Quarterly/Yearly):**
- `tdau_avg_m`, `equity_m`, `equity_filtered_m`
- `tdau_avg_q`, `equity_q`, `equity_filtered_q`
- `tdau_avg_y`, `equity_y`, `equity_filtered_y`

---

### 3.2 Target & Progress Tables

**`gbis.biz.dim_kpi_target`** - Quarterly targets by brand
- Columns: `brand`, `date_q`, `date_y`, `nrfr_target_b`, `nrfr_target_a`
- **`date_q`是字符串格式**：`'2026_Q1'`, `'2026_Q2'` 等
- 过滤/匹配时注意类型一致：可通过主表date_q列直接JOIN，或用`CONCAT(YEAR(CURRENT_DATE()),'_Q',QUARTER(CURRENT_DATE()))`构造匹配字符串
- APAC和VTJ合并为 `brand = 'APAC + VTJ'`，其他品牌独立存储
- **必须在一条SQL里JOIN**，不要分开查再手动拼接

**`gbis.biz.dim_date_progress_metrics`** - Date progress tracking
- Columns: `date`, `quarter_progress`, `year_progress`
- quarter_progress表示当前日期在本季度中的进度比例（0~1），用于计算QTD目标：target_qtd = target_q * quarter_progress

---

### 3.3 STAR Brand Dashboard Tables (Pre-aggregated, STAR-only)

**`gbis.biz.dashboard_star_sales_metrics_daily`**
- Already filtered for STAR - NO `crm_server_id` filter needed
- NO `user_id` column (pre-aggregated)
- Date column: `date` (NOT report_date!)
- Withdrawal column: `withdrawal`
- Deposits: `gross_deposit`, `net_deposit` (NO column named just "deposit"!)
- Has: `country`, `client_type`, `account_type`, `sales_name`, `sales_org_name`
- Has: `trading_volume`, `ftd`, `ftd_amount`, `ftt`, `ftt_amount`
- Revenue: `risk_revenue`, `risk_free_revenue`, `gross_company_pnl`, `net_company_pnl`
- Components: `spread_revenue`, `commission_revenue`, `swaps_revenue`, `dividend_revenue`, `rollover_revenue`
- Rebates: `ib_rebate`, `cpa_rebate`
- RLS fields: `has_emma`, `has_harry`, `has_adam`, `has_jennie`, `has_luke`, `has_phil`, `has_john`, `has_jay`, `has_mandy`, `has_moe`, `has_jeff`, `has_yazan`, `has_lewis`, `has_vd`

**`gbis.biz.dashboard_star_fact_daily_kpi`** - Source for sales_metrics (event + trading)

---

### 3.4 Source Tables (User-Level, Granular)

**`platinum.gbis.dws_login_metrics_daily`** - Daily trading metrics per user
- HAS `user_id`, `login`, `server_id`, `crm_server_id`
- Date column: `date`
- Withdrawal column: `withdraw` (NOT "withdrawal"! Different spelling!)
- Deposits: `gross_deposit`, `net_deposit`
- Revenue columns: same names as aggregated tables
- Filter for STAR: `WHERE crm_server_id = 1010`

**`platinum.gbis.dim_user_base_daily_snapshot`** - User dimension
- Columns: `user_id`, `ftd_date`, `register_date`, `live_date`, `ftt_date`, `live_kyc_date`, `country`, `crm_server_id`
- NO `snapshot_date` column! Use `ftd_date` or `register_date` for date filtering.

**`platinum.gbis.dim_login_ownership_monthly`** - Sales/ownership attribution
- Join key: `login`, `server_id`, `month`
- Has: `brand`, `client_type`, `sales_id`, `sales_name`, `sales_org_name`, `cpa_id`, `account_group_category_3` (= account_type)

**`platinum.gbis.dim_user_ownership_monthly`** - User-level ownership
- Join key: `user_id`, `crm_server_id`, `month`

---

### 3.5 Symbol/Instrument Tables

**`gbis.biz.dws_txau_by_symbol_di`** - Trading users by symbol/asset type (aggregated, preferred)
- Column is `symbol_asset_type` (NOT "symbol"!)
- Columns: `date`, `brand`, `symbol_asset_type`, `is_inst`, `user_count`, `trading_volume`, `period`, `client_type`, `second_region_name`, `country`, `spread_revenue`, `risk_free_revenue`, `risk_revenue`
- This is the PRIMARY table for symbol queries. Use it first.
- Limitation: may not have weekend/recent dates. If query returns empty or date range has no data, fallback to the table below.

**`platinum.gbis.dws_login_symbol_metrics_daily`** - Login-level symbol metrics (fallback, granular)
- Columns: `date`, `brand`, `symbol_asset_type`, `symbol`, `trading_volume` (and others)
- Use this as FALLBACK when `dws_txau_by_symbol_di` returns empty for the requested date range.
- Must GROUP BY to aggregate (this is login-level, not pre-aggregated).

**Date/Time important notes:**
- Databricks DAYOFWEEK: Sunday=1, Monday=2, Tuesday=3, Wednesday=4, Thursday=5, Friday=6, Saturday=7
- Weekend filter: `DAYOFWEEK(date) IN (1, 7)` (Sunday + Saturday)
- Weekday filter: `DAYOFWEEK(date) BETWEEN 2 AND 6` (Monday–Friday)

**Symbol/Instrument important notes:**
- `symbol_asset_type = 'Gold'` — traditional gold (XAUUSD etc.), NO trading on weekends
- `symbol_asset_type = '247 Gold'` — 7x24 product (XAUUSD247), trades on weekends
- CRITICAL filtering rules:
  - User asks "247 Gold" specifically → exact match `symbol_asset_type = '247 Gold'`
  - User asks "Gold" or "黄金" (generic) → use `LIKE '%Gold%'` to get BOTH, then in the answer ALWAYS break down and compare "Gold" vs "247 Gold" separately (show both, discuss differences)
  - Weekend gold trading data comes from "247 Gold" only — clarify this in the answer

**`gbis.biz.dws_tdau_by_brand_di`** - Trading DAU by brand
- Columns: `date`, `client_type`, `second_region_name`, `is_inst`, `brand`, `country`, `user_type`, `user_count`

---

### 3.6 Cohort Analysis

**`gbis.biz.dws_user_ftd_cohort_metrics_v2_df`** - FTD cohort
- Columns: `month_index`, `trader_count`, `gross_deposit_accum`, `net_deposit_rt_accum`, `brand`, `client_type`, `deposit_count`, `net_deposit_accum`, `ftd_month`, `ftd_count`, `net_deposit`, `trading_volume`, `country`, `second_region_name`, `gross_deposit`

---

## 4. Table Selection Guide

| Question Type | Table to Use |
|--------------|-------------|
| Any brand KPI (simple) | `gbis.biz.ads_kpi_summary_daily` |
| STAR sales/financial (aggregated) | `gbis.biz.dashboard_star_sales_metrics_daily` |
| STAR user events (register/FTD/FTT) | `gbis.biz.dashboard_star_fact_daily_kpi` |
| User-level analysis (need user_id) | `platinum.gbis.dws_login_metrics_daily` + joins |
| New vs existing user segmentation | Source tables with `dim_user_base_daily_snapshot` |
| Symbol/instrument concentration | `gbis.biz.dws_txau_by_symbol_di` |
| Trading DAU breakdown | `gbis.biz.dws_tdau_by_brand_di` |
| FTD cohort retention | `gbis.biz.dws_user_ftd_cohort_metrics_v2_df` |
| Targets and progress | `gbis.biz.dim_kpi_target` + `dim_date_progress_metrics` |

---

## 5. Databricks SQL Rules

### Date Functions (CRITICAL)
```sql
-- Today's date
CURRENT_DATE()                              -- Correct
-- WRONG: CURDATE(), NOW()

-- Days arithmetic
DATE_SUB(CURRENT_DATE(), 30)               -- 30 days ago
DATE_ADD(CURRENT_DATE(), 7)                -- 7 days from now

-- Month/year arithmetic
ADD_MONTHS(CURRENT_DATE(), -1)             -- 1 month ago
ADD_MONTHS(CURRENT_DATE(), -6)             -- 6 months ago
ADD_MONTHS(CURRENT_DATE(), -12)            -- 1 year ago
-- WRONG: DATEADD(), INTERVAL syntax

-- Date truncation (unit MUST be quoted!)
DATE_TRUNC('MONTH', date)                  -- First day of month
DATE_TRUNC('QUARTER', date)                -- First day of quarter
DATE_TRUNC('YEAR', date)                   -- First day of year
DATE_TRUNC('WEEK', date)                   -- First day of week
-- WRONG: DATE_TRUNC(MONTH, date) without quotes

-- Date formatting
DATE_FORMAT(date, 'yyyy-MM')               -- "2026-04"
DATE_FORMAT(date, 'yyyy-MM-dd')            -- "2026-04-14"

-- Date parts
YEAR(date), MONTH(date), DAY(date)
DAYOFWEEK(date)                            -- 1=Sunday, 2=Monday, ..., 7=Saturday
```

### Common WHERE Clause Patterns
```sql
WHERE date >= DATE_SUB(CURRENT_DATE(), 30)           -- Last 30 days
WHERE date >= ADD_MONTHS(CURRENT_DATE(), -3)         -- Last 3 months
WHERE date >= ADD_MONTHS(CURRENT_DATE(), -12)        -- Last year
WHERE date >= DATE_TRUNC('MONTH', CURRENT_DATE())    -- Current month
WHERE date >= DATE_TRUNC('YEAR', CURRENT_DATE())     -- Year to date
```

### Column Alias Rule
NEVER alias an aggregation with the same name as the source column. Databricks throws MISSING_ATTRIBUTES error.
```sql
-- WRONG:
SUM(net_deposit) AS net_deposit

-- CORRECT:
SUM(net_deposit) AS total_net_deposit
```
Always prefix: `total_`, `avg_`, `sum_`, etc.

### Column Name Gotchas
| Pitfall | Rule |
|---------|------|
| `swaps_revenue` | PLURAL with 's' - never `swap_revenue` |
| `withdrawal` vs `withdraw` | Dashboard tables = `withdrawal`, Source tables = `withdraw` |
| "deposit" alone | Does NOT exist as column. Always `gross_deposit` or `net_deposit` |
| `front_end_ecost` | Exact name, no abbreviation |
| `symbol_asset_type` | NOT "symbol" |

### Data Quality Filters
```sql
WHERE country IS NOT NULL AND country != 'Others'   -- Exclude invalid
WHERE brand NOT IN ('Others', 'BYBIT')              -- Standard exclusion
```

---

## 6. Key Query Patterns

### NRFR with Targets and Progress
```sql
SELECT
  t1.*,
  SUM(nrfr) OVER(PARTITION BY t1.brand, t1.date_y, t1.date_q ORDER BY t1.date) AS nrfr_accum,
  t2.nrfr_target_b AS nrfr_target_b_q,
  t2.nrfr_target_b * t3.quarter_progress AS nrfr_target_b_qtd,
  quarter_progress
FROM (
  SELECT 
    CASE WHEN brand IN ('APAC','VTJ') THEN 'APAC + VTJ' ELSE brand END AS brand,
    date_y, date_q, date,
    SUM(front_end_ecost_daily_report) AS front_end_ecost,
    SUM(risk_free_revenue) AS rfr,
    SUM(risk_free_revenue) - SUM(front_end_ecost) AS nrfr
  FROM gbis.biz.ads_kpi_summary_daily
  WHERE date >= '2026-01-01' AND brand NOT IN ('Others', 'BYBIT')
  GROUP BY 1, 2, 3, 4
) t1
LEFT JOIN gbis.biz.dim_kpi_target t2 ON t1.brand = t2.brand AND t1.date_q = t2.date_q
LEFT JOIN gbis.biz.dim_date_progress_metrics t3 ON t1.date = t3.date
ORDER BY date DESC
```

### New vs Existing User Analysis
```sql
SELECT
    t.date,
    CASE
        WHEN u.ftd_date BETWEEN '2026-01-01' AND CURRENT_DATE() THEN 'New User'
        WHEN u.ftd_date < '2026-01-01' THEN 'Existing User'
        ELSE 'Unknown'
    END AS user_cohort,
    COUNT(DISTINCT t.user_id) as user_count,
    ABS(SUM(t.withdraw)) as total_withdrawal
FROM platinum.gbis.dws_login_metrics_daily t
LEFT JOIN platinum.gbis.dim_user_base_daily_snapshot u
    ON t.user_id = u.user_id AND t.crm_server_id = u.crm_server_id
WHERE t.crm_server_id = 1010
    AND u.ftd_date IS NOT NULL
GROUP BY 1, 2
ORDER BY t.date DESC
```

### Symbol Concentration Analysis
```sql
WITH symbol_metrics AS (
  SELECT symbol_asset_type, SUM(trading_volume) AS volume, SUM(spread_revenue) AS revenue
  FROM gbis.biz.dws_txau_by_symbol_di
  WHERE brand = 'STAR' AND date >= DATE_SUB(CURRENT_DATE(), 90)
  GROUP BY symbol_asset_type
)
SELECT symbol_asset_type, volume, revenue,
  ROUND(volume * 100.0 / SUM(volume) OVER(), 2) AS pct_volume,
  ROUND(SUM(volume) OVER(ORDER BY volume DESC) * 100.0 / SUM(volume) OVER(), 2) AS cumulative_pct
FROM symbol_metrics
ORDER BY volume DESC
LIMIT 30
```

---

## 7. Semantic Mapping (User Language -> SQL)

| User Says | Actual Column / Formula |
|-----------|------------------------|
| "NDM" | `(SUM(net_deposit) + SUM(rt)) / NULLIF(SUM(gross_deposit), 0)` (ads_kpi table; use `rt_value` for dashboard_star table) |
| "NRFR" | `risk_free_revenue - front_end_ecost` |
| "revenue" | Usually `risk_free_revenue` (clarify if ambiguous) |
| "deposit" alone | Default to `gross_deposit` |
| "withdraw" or "withdrawal" | Same metric, column name depends on table |
| "ftd time" | `ftd_date` column |
| "ftt time" | `ftt_date` column |
| "register time" | `register_date` |
| Chinese input | Respond in Chinese |

---

## 8. Output Rules

- All monetary values display in USD ($). Never use other currency symbols even for regional data.
- STAR brand filter: `crm_server_id = 1010` (source tables only)
- When comparing brands: use `gbis.biz.ads_kpi_summary_daily` with `GROUP BY brand`
- Weekday-only analysis: add `WHERE DAYOFWEEK(date) BETWEEN 2 AND 6`

---

## 9. Infrastructure & Credentials

### Databricks Connection
```
Server Hostname: ${DATABRICKS_HOST}
HTTP Path:       ${DATABRICKS_HTTP_PATH}
Access Token:    ${DATABRICKS_TOKEN}
Catalog:         gbis
Schema:          biz
```

Python connection:
```python
from databricks import sql as databricks_sql

connection = databricks_sql.connect(
    server_hostname=os.getenv("DATABRICKS_HOST"),
    http_path=os.getenv("DATABRICKS_HTTP_PATH"),
    access_token=os.getenv("DATABRICKS_TOKEN")
)
```

### AWS Bedrock (AI Model)
```
Provider:        AWS Bedrock
Region:          us-east-1
Model ID:        us.anthropic.claude-opus-4-6-v1
AWS Access Key:  ${AWS_ACCESS_KEY_ID}
AWS Secret Key:  ${AWS_SECRET_ACCESS_KEY}
```

Python connection:
```python
import boto3

session = boto3.Session(
    region_name='us-east-1',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)
bedrock = session.client('bedrock-runtime')
```

### EC2 Deployment (Dashboard)
```
Host:            18.136.250.8
User:            ec2-user
App Path:        /home/ec2-user/gbis-analysis/
Service:         sudo systemctl restart gbis-analysis
URL:             http://18.136.250.8/gbis-analysis/
Port:            5000 (gunicorn)
Nginx:           Docker container "migration-nginx"
```

---

## 10. Query Execution Config

- Query timeout: 30 seconds
- Max rows returned: 10,000
- Databricks SQL connector: `databricks-sql-connector` Python package
