---
description: Universal Queries for All Brands - KPI Summary and Analytics
tables: [gbis.biz.ads_kpi_summary_daily, gbis.biz.dim_kpi_target, gbis.biz.dim_date_progress_metrics, gbis.biz.dws_txau_by_symbol_di, gbis.biz.dws_tdau_by_brand_di, gbis.biz.dws_user_ftd_cohort_metrics_v2_df]
priority: universal
---

## Description

These queries work across ALL brands (STAR, APAC, VTJ, etc.) using the universal KPI summary table. The key difference from brand-specific queries is:
- **Filter by brand name** using `WHERE brand = 'STAR'` instead of using brand-specific tables
- Use `gbis.biz.ads_kpi_summary_daily` as the main table
- Has extended columns including DAU metrics, front-end costs, and commission breakdown

## Critical Information

### Main Tables:
- **gbis.biz.ads_kpi_summary_daily** - Main KPI summary table for all brands
- **gbis.biz.dim_kpi_target** - Target metrics by brand and quarter
- **gbis.biz.dim_date_progress_metrics** - Date progress tracking (quarter_progress, year_progress)
- **gbis.biz.dws_txau_by_symbol_di** - Trading users by symbol/asset type
- **gbis.biz.dws_tdau_by_brand_di** - Trading DAU by brand
- **gbis.biz.dws_user_ftd_cohort_metrics_v2_df** - FTD cohort analysis

### Extended Columns in ads_kpi_summary_daily:
**Core Metrics:**
- date, date_mm (month), date_y (year), date_q (quarter)
- brand, client_type, country, second_region_name, is_inst

**User & Activity Metrics:**
- register_count, live_count, ftd_count, ftt_count
- tdau, tdau_wo_toc, tdau_fix, tdau_wo_toc_fix (Trading DAU variations)
- funding_dau (Funding DAU)
- mau (Monthly Active Users)

**Financial Metrics:**
- gross_deposit, net_deposit, withdrawal
- trading_volume, trading_volume_wo_toc
- rt (net deposit rate), equity, equity_filtered

**Revenue Components (EXACT column names):**
- spread_revenue
- commission_revenue
- swaps_revenue (plural with 's'!)
- dividend_revenue
- rollover_revenue
- risk_free_revenue (sum of above 5 components)
- risk_revenue

**PnL Metrics:**
- net_company_pnl, gross_company_pnl, gross_client_pnl

**Costs & Commissions:**
- front_end_ecost (Front-end effective cost)
- front_end_ecost_daily_report (Daily report version)
- ib_rebate (IB rebates)
- cpa_commission (CPA commissions)
- sales_commission (Sales commissions)
- sales_commission_nd (Sales commission - net deposit)
- psp_charge (Payment service provider charges)

**Aggregated Metrics (Monthly/Quarterly/Yearly):**
- tdau_avg_m, equity_m, equity_filtered_m (monthly)
- tdau_avg_q, equity_q, equity_filtered_q (quarterly)
- tdau_avg_y, equity_y, equity_filtered_y (yearly)

### Business Formulas:

**NDM (Net Deposit Margin) - NOT "Net Deposit Money"!:**
```
NDM = net_deposit / gross_deposit   (it is a RATIO, not an amount!)
```
CRITICAL: When user asks for "NDM", ALWAYS calculate as a ratio:
`ROUND(SUM(net_deposit) / NULLIF(SUM(gross_deposit), 0), 4) AS NDM`
NDM is NOT the same as net_deposit! NDM is a margin/ratio between net_deposit and gross_deposit.

**NRFR (Net Risk-Free Revenue):**
```
NRFR = risk_free_revenue - front_end_ecost
```

**RFR (Risk-Free Revenue):**
```
RFR = risk_free_revenue
```

**Risk-Free Revenue Components:**
```
risk_free_revenue = spread_revenue + commission_revenue + swaps_revenue + dividend_revenue + rollover_revenue
```

### Brand Name Mapping (CRITICAL - use EXACT database names!):
| User says | Database brand name |
|-----------|-------------------|
| STAR, StarTrader | `STAR` |
| VT, VT Markets | `VT` |
| PU, PU Prime | `PU` |
| MM, Moneta Markets | `MM` |
| UM, Ultima Markets | `UM` |
| APAC | `APAC` |
| GS | `GS` |
| VTJ | `VTJ` |

**All brand values in database: APAC, BYBIT, GS, MM, PU, STAR, UM, VT, VTJ**

### Region Name Mapping:
| User says | Database second_region_name |
|-----------|---------------------------|
| EU, Europe | `Europe` |
| Asia | `Asia` |
| LATAM, Latin America | `LATAM` |
| MENA, Middle East | `MENA` |

**All region values in database: Asia, BYBIT, Europe, LATAM, MENA, Others**

### How to Filter by Brand:
```sql
WHERE brand = 'STAR'  -- For STAR/StarTrader
WHERE brand = 'VT'    -- For VT Markets
WHERE brand = 'PU'    -- For PU Prime
WHERE brand IN ('GS', 'STAR', 'VT', 'PU')  -- Multiple brands
WHERE brand NOT IN ('Others', 'BYBIT')  -- Exclude
```

## Sample Natural Language Questions

- "Show me STAR brand's daily TDAU and MAU trends for the last 3 months"
- "Analyze NRFR (net risk-free revenue) for STAR from Jan to Apr 2026"
- "Compare STAR's revenue components (spread, commission, swaps, etc.) by country"
- "What's STAR's withdrawal trend by week in Q1 2026?"
- "Show me STAR brand health metrics: NRFR, TDAU, equity, and revenue breakdown"
- "Compare STAR vs APAC brand performance on key metrics"
- "What's the FTD cohort performance for STAR users who registered in Jan 2026?"
- "Show STAR's progress toward quarterly NRFR targets"
- "What are the top 20 symbols by trading volume and revenue for STAR?"
- "Analyze symbol concentration - which instruments drive most of STAR's revenue?"
- "Show revenue breakdown by symbol_asset_type for STAR brand"

## Example SQL Queries

### Query 1: Daily KPI Summary with All Columns

```sql
SELECT
  date,
  date_mm,
  brand,
  client_type,
  country,
  second_region_name,
  is_inst,
  register_count, 
  live_count,
  ftd_count, 
  ftt_count, 
  gross_deposit,
  net_deposit,
  withdrawal,
  trading_volume,
  trading_volume_wo_toc,
  tdau, 
  tdau_wo_toc,
  tdau_fix, 
  tdau_wo_toc_fix,
  funding_dau,
  mau,
  rt,
  equity,
  equity_filtered,
  net_company_pnl,
  gross_company_pnl,
  gross_client_pnl,
  ib_rebate,
  cpa_commission,
  sales_commission,
  spread_revenue,
  commission_revenue,
  swaps_revenue,
  dividend_revenue,
  rollover_revenue,
  risk_free_revenue,
  risk_revenue,
  front_end_ecost_daily_report,
  front_end_ecost,
  sales_commission_nd,
  psp_charge,
  tdau_avg_m, 
  equity_m,
  equity_filtered_m,
  tdau_avg_q, 
  equity_q,
  equity_filtered_q,
  tdau_avg_y,
  equity_y,
  equity_filtered_y,
  IF(DAYOFWEEK(date) BETWEEN 2 AND 6, 1, 0) AS date_type
FROM gbis.biz.ads_kpi_summary_daily
WHERE date >= '2025-01-01' 
  AND brand = 'STAR'
ORDER BY date DESC
```

### Query 2: NRFR Tracking with Targets and Progress

```sql
SELECT
  t1.*,
  SUM(nrfr) OVER(PARTITION BY t1.brand, t1.date_y, t1.date_q ORDER BY t1.date) AS nrfr_accum,
  SUM(rfr) OVER(PARTITION BY t1.brand, t1.date_y, t1.date_q ORDER BY t1.date) AS rfr_accum,
  SUM(front_end_ecost) OVER(PARTITION BY t1.brand, t1.date_y, t1.date_q ORDER BY t1.date) AS front_end_ecost_accum,
  t2.nrfr_target_b AS nrfr_target_b_q,
  t2.nrfr_target_a AS nrfr_target_a_q,
  t2.nrfr_target_b * t3.quarter_progress AS nrfr_target_b_qtd,
  t2.nrfr_target_a * t3.quarter_progress AS nrfr_target_a_qtd,
  quarter_progress,
  t4.nrfr_target_b * t3.year_progress AS nrfr_target_b_ytd,
  t4.nrfr_target_a * t3.year_progress AS nrfr_target_a_ytd,
  year_progress
FROM (
  SELECT 
    CASE WHEN brand IN ('APAC','VTJ') THEN 'APAC + VTJ' ELSE brand END AS brand,
    date_y,
    date_q,
    date,
    SUM(front_end_ecost_daily_report) AS front_end_ecost,
    SUM(risk_free_revenue) AS rfr,
    SUM(risk_free_revenue) - SUM(front_end_ecost) AS nrfr
  FROM gbis.biz.ads_kpi_summary_daily
  WHERE date >= '2026-01-01'
    AND brand NOT IN ('Others', 'BYBIT')
  GROUP BY 1, 2, 3, 4
) t1
LEFT JOIN gbis.biz.dim_kpi_target t2
  ON t1.brand = t2.brand AND t1.date_q = t2.date_q
LEFT JOIN gbis.biz.dim_date_progress_metrics t3
  ON t1.date = t3.date
LEFT JOIN (
  SELECT 
    brand,
    date_y,
    SUM(nrfr_target_b) AS nrfr_target_b,
    SUM(nrfr_target_a) AS nrfr_target_a
  FROM gbis.biz.dim_kpi_target
  GROUP BY 1, 2
) t4 
  ON t1.brand = t4.brand AND t1.date_y = t4.date_y
ORDER BY date DESC
```

### Query 3: Trading Users by Symbol/Asset Type

```sql
SELECT 
  date, 
  symbol_asset_type, 
  is_inst, 
  brand, 
  user_count, 
  trading_volume, 
  period, 
  client_type, 
  second_region_name, 
  country, 
  spread_revenue, 
  risk_free_revenue, 
  risk_revenue,
  IF(DAYOFWEEK(date) BETWEEN 2 AND 6, 1, 0) AS date_type,
  DATE_FORMAT(date, 'yyyy-MM') AS Month
FROM gbis.biz.dws_txau_by_symbol_di
WHERE brand = 'STAR'
  AND date >= '2026-01-01'
ORDER BY date DESC
```

### Query 4: Trading DAU by Brand

```sql
SELECT 
  date, 
  client_type, 
  second_region_name, 
  is_inst, 
  brand, 
  country, 
  user_type, 
  user_count,
  IF(DAYOFWEEK(date) BETWEEN 2 AND 6, 1, 0) AS date_type
FROM gbis.biz.dws_tdau_by_brand_di
WHERE brand = 'STAR'
  AND date >= '2026-01-01'
ORDER BY date DESC
```

### Query 5: FTD Cohort Analysis

```sql
SELECT  
  month_index, 
  trader_count, 
  gross_deposit_accum, 
  net_deposit_rt_accum, 
  brand, 
  client_type, 
  deposit_count, 
  net_deposit_accum, 
  ftd_month, 
  ftd_count, 
  net_deposit, 
  trading_volume, 
  country, 
  second_region_name, 
  gross_deposit
FROM gbis.biz.dws_user_ftd_cohort_metrics_v2_df
WHERE brand = 'STAR'
  AND ftd_month >= '2026-01'
ORDER BY ftd_month DESC, month_index
```

### Query 6: Symbol/Instrument Concentration Analysis

**CRITICAL: Column name is `symbol_asset_type` (NOT "symbol"!)**

```sql
-- Top symbols by trading volume and revenue
SELECT 
  symbol_asset_type,
  SUM(user_count) AS total_users,
  SUM(trading_volume) AS total_volume,
  SUM(spread_revenue) AS total_spread_revenue,
  SUM(risk_free_revenue) AS total_risk_free_revenue,
  SUM(risk_revenue) AS total_risk_revenue
FROM gbis.biz.dws_txau_by_symbol_di
WHERE brand = 'STAR'
  AND date >= DATE_SUB(CURRENT_DATE(), 90)
GROUP BY symbol_asset_type
ORDER BY total_volume DESC
LIMIT 20
```

**Calculate concentration (cumulative percentage):**
```sql
WITH symbol_metrics AS (
  SELECT 
    symbol_asset_type,
    SUM(trading_volume) AS volume,
    SUM(spread_revenue) AS revenue
  FROM gbis.biz.dws_txau_by_symbol_di
  WHERE brand = 'STAR'
    AND date >= DATE_SUB(CURRENT_DATE(), 90)
  GROUP BY symbol_asset_type
),
ranked AS (
  SELECT 
    symbol_asset_type,
    volume,
    revenue,
    SUM(volume) OVER () AS total_volume,
    SUM(revenue) OVER () AS total_revenue,
    ROW_NUMBER() OVER (ORDER BY volume DESC) AS rank
  FROM symbol_metrics
)
SELECT 
  rank,
  symbol_asset_type,
  volume,
  revenue,
  ROUND(volume * 100.0 / total_volume, 2) AS pct_volume,
  ROUND(revenue * 100.0 / total_revenue, 2) AS pct_revenue,
  ROUND(SUM(volume) OVER (ORDER BY rank) * 100.0 / total_volume, 2) AS cumulative_pct_volume,
  ROUND(SUM(revenue) OVER (ORDER BY rank) * 100.0 / total_revenue, 2) AS cumulative_pct_revenue
FROM ranked
ORDER BY rank
LIMIT 30
```

## Expected Output Columns

The queries return comprehensive KPI data including:
- Time dimensions (date, month, quarter, year)
- Segmentation (brand, country, client_type, is_inst)
- User metrics (registers, live, FTD, FTT, TDAU, MAU)
- Financial metrics (deposits, withdrawals, revenue components)
- Performance indicators (NRFR, targets, progress)

## Business Context

**Universal Table Advantage:**
- One query works for all brands - just change the brand filter
- Pre-aggregated daily metrics for fast query performance
- Extended column set includes DAU metrics and cost breakdown
- Integrated with target tracking and progress metrics

**Key Metrics:**
- **TDAU** (Trading DAU): Active trading users per day
- **NRFR** (Net Risk-Free Revenue): Revenue after front-end costs
- **Front-end ecost**: Marketing and acquisition costs
- **MAU** (Monthly Active Users): 30-day active user count

**Date Type Flag:**
```sql
IF(DAYOFWEEK(date) BETWEEN 2 AND 6, 1, 0) AS date_type
```
This flags weekdays (Mon-Fri) as 1, weekends as 0 for weekday-only analysis.

## Important Notes

1. **Always filter by brand name**: `WHERE brand = 'STAR'` instead of using brand-specific tables
2. **Use exact column names**: `swaps_revenue` (plural), `front_end_ecost`, not abbreviations
3. **NRFR calculation**: `risk_free_revenue - front_end_ecost`
4. **Withdrawals**: Stored as NEGATIVE values, use `ABS(SUM(withdrawal))` for totals
5. **Date filters**: Use `date >= '2026-01-01'` format for date ranges
6. **Brand combinations**: Some brands can be combined (APAC + VTJ) for analysis

## CRITICAL: Databricks SQL Date Function Syntax

**Always use these EXACT patterns:**

```sql
-- ✅ CORRECT - Today's date:
CURRENT_DATE()                            -- Use this!

-- ❌ WRONG - Don't use:
CURDATE()                                 -- MySQL syntax, not Databricks!
NOW()                                     -- Returns timestamp, not date

-- ✅ CORRECT - Date arithmetic (days):
DATE_SUB(CURRENT_DATE(), 30)             -- 30 days ago
DATE_SUB(CURRENT_DATE(), 90)             -- 90 days ago
DATE_ADD(CURRENT_DATE(), 7)              -- 7 days from now

-- ✅ CORRECT - Date arithmetic (months/years):
ADD_MONTHS(CURRENT_DATE(), -1)           -- 1 month ago
ADD_MONTHS(CURRENT_DATE(), -6)           -- 6 months ago
ADD_MONTHS(CURRENT_DATE(), -12)          -- 12 months ago (1 year)
ADD_MONTHS(CURRENT_DATE(), -24)          -- 24 months ago (2 years)

-- ❌ WRONG - Don't use INTERVAL syntax:
DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)     -- ERROR!
DATE_ADD(date, INTERVAL -1 YEAR)              -- ERROR!
INTERVAL -1 YEAR                              -- ERROR!
DATEADD('month', -6, CURRENT_DATE())          -- ERROR!

-- ✅ CORRECT - Date truncation (unit MUST be quoted):
DATE_TRUNC('MONTH', date)                -- First day of month
DATE_TRUNC('QUARTER', date)              -- First day of quarter
DATE_TRUNC('YEAR', date)                 -- First day of year
DATE_TRUNC('WEEK', date)                 -- First day of week

-- ❌ WRONG - Unit without quotes:
DATE_TRUNC(MONTH, date)                  -- ERROR! Must quote 'MONTH'
DATE_TRUNC(YEAR, date)                   -- ERROR! Must quote 'YEAR'

-- ✅ CORRECT - Date formatting:
DATE_FORMAT(date, 'yyyy-MM')             -- "2026-04"
DATE_FORMAT(date, 'yyyy-MM-dd')          -- "2026-04-14"

-- ✅ CORRECT - Extract date parts:
YEAR(date)                               -- 2026
MONTH(date)                              -- 4
DAY(date)                                -- 14
DAYOFWEEK(date)                          -- 1=Sunday, 2=Monday, ..., 7=Saturday
```

**Examples in WHERE clauses:**
```sql
-- Last 30 days:
WHERE date >= DATE_SUB(CURRENT_DATE(), 30)

-- Last 3 months:
WHERE date >= ADD_MONTHS(CURRENT_DATE(), -3)

-- Last year:
WHERE date >= ADD_MONTHS(CURRENT_DATE(), -12)

-- Current month:
WHERE date >= DATE_TRUNC('MONTH', CURRENT_DATE())

-- Current year to date:
WHERE date >= DATE_TRUNC('YEAR', CURRENT_DATE())
```
