from pyspark.sql import SparkSession
from datetime import datetime, timedelta
import sys

sys.path.append("/Workspace/github/pulse/")

from modules.datamart.utils import create_table, optimize_table, validate_source_data, run_etl

TARGET_TABLE = "gbis.biz.dashboard_star_fact_daily_kpi"
DEFAULT_START_DATE = "2025-01-01"
spark = SparkSession.builder \
    .appName("Star_Fact_Daily_KPI") \
    .enableHiveSupport() \
    .getOrCreate()

print(f"✓ Spark session initialized")
print(f"✓ Target table: {TARGET_TABLE}")

cols = {
    # Date
    "date": "DATE",

    # Sales
    "sales_id": "BIGINT",
    "p_ids": "STRING",

    # Core dimensions
    "country": "STRING",
    "account_type": "STRING",
    "client_type": "STRING",
    "sales_org_id": "BIGINT",
    "sales_org_name": "STRING",
    "sales_name": "STRING",
    "cpa_id": "BIGINT",
    "cpa_name": "STRING",
    "master_ib_id": "BIGINT",
    "master_ib_name": "STRING",
    "ib_affid": "BIGINT",
    "ib_name": "STRING",

    # Event metrics
    "register": "INT",
    "live": "INT",
    "live_kyc": "INT",
    "ftd": "INT",
    "ftd_amount": "DOUBLE",
    "ftt": "INT",
    "ftt_amount": "DOUBLE",

    # Trading metrics
    "gross_deposit": "DOUBLE",
    "withdrawal": "DOUBLE",
    "net_deposit": "DOUBLE",
    "rt_value": "DOUBLE",
    "gross_deposit_rt": "DOUBLE",
    "net_deposit_rt": "DOUBLE",
    "t_dau": "INT",
    "trading_volume": "DOUBLE",
    "ib_rebate": "DOUBLE",
    "cpa_rebate": "DOUBLE",
    "gross_company_pnl": "DOUBLE",
    "net_company_pnl": "DOUBLE",
    "spread_revenue": "DOUBLE",
    "commission_revenue": "DOUBLE",
    "swaps_revenue": "DOUBLE",
    "dividend_revenue": "DOUBLE",
    "rollover_revenue": "DOUBLE",
    "risk_free_revenue": "DOUBLE",
    "risk_revenue": "DOUBLE",
    "equity": "DOUBLE",

    # Sales hierarchy
    "level1": "STRING",
    "level2": "STRING",
    "level3": "STRING",
    "level4": "STRING",
    "level5": "STRING",
    "level6": "STRING",
    "level7": "STRING",

    # RLS fields
    "has_emma": "BOOLEAN",
    "has_harry": "BOOLEAN",
    "has_adam": "BOOLEAN",
    "has_jennie": "BOOLEAN",
    "has_luke": "BOOLEAN",
    "has_phil": "BOOLEAN",
    "has_john": "BOOLEAN",
    "has_jay": "BOOLEAN",
    "has_mandy": "BOOLEAN",
    "has_moe": "BOOLEAN",
    "has_jeff": "BOOLEAN",
    "has_yazan": "BOOLEAN",
    "has_lewis": "BOOLEAN",
    "has_vd": "BOOLEAN"
}

def get_etl_query(start_date: str = DEFAULT_START_DATE):
    return f"""
        WITH org as (
            select *
            from gbis.prod.dim_sales_org_level_daily
            where `date` = (select max(date) from gbis.prod.dim_sales_org_level_daily)
            and source_server = 'crm_startrader'
        ),
        raw AS (
            SELECT
                user_id,
                coalesce(country, 'Others') as country,
                crm_server_id,
                register_date,
                live_date,
                live_kyc_date,
                ftd_date,
                first_deposit_amount_usd,
                ftt_date,
                first_trade_amount_usd
            FROM platinum.gbis.dim_user_base_daily_snapshot
            WHERE crm_server_id = 1010 -- STAR
        ),
        event AS (
            SELECT user_id, country, crm_server_id, 'register' AS event, register_date AS event_date, CAST(NULL AS DOUBLE) AS event_amount
            FROM raw WHERE register_date IS NOT NULL
                UNION ALL
            SELECT user_id, country, crm_server_id, 'live', live_date, CAST(NULL AS DOUBLE)
            FROM raw WHERE live_date IS NOT NULL
                UNION ALL
            SELECT user_id, country, crm_server_id, 'live_kyc', live_kyc_date, CAST(NULL AS DOUBLE)
            FROM raw WHERE live_kyc_date IS NOT NULL
                UNION ALL
            SELECT user_id, country, crm_server_id, 'ftd', ftd_date, first_deposit_amount_usd
            FROM raw WHERE ftd_date IS NOT NULL
                UNION ALL
            SELECT user_id, country, crm_server_id, 'ftt', ftt_date, first_trade_amount_usd
            FROM raw WHERE ftt_date IS NOT NULL
        ),
        event_attr AS (
            SELECT
                e.country,
                e.event,
                e.event_date AS date,
                e.event_amount,
                COALESCE(um.cpa_sales_id, um.sales_id) AS sales_id,
                COALESCE(um.cpa_sales_p_ids, um.p_ids) AS p_ids,
                COALESCE(um.cpa_sales_org_id, um.sales_org_id) AS sales_org_id,
                COALESCE(um.cpa_sales_org_name, um.sales_org_name) AS sales_org_name,
                COALESCE(um.cpa_sales_name, um.sales_name) AS sales_name,
                'Retail' AS account_type,
                um.client_type,
                um.cpa_id,
                um.cpa_name,
                um.user_master_ib_id AS master_ib_id,
                um.user_master_ib_name AS master_ib_name,
                um.user_direct_ib_affid AS ib_affid,
                um.user_direct_ib_name AS ib_name
            FROM event e
            LEFT JOIN platinum.gbis.dim_user_ownership_monthly um
                ON e.user_id = um.user_id
                AND e.crm_server_id = um.crm_server_id
                AND date_format(e.event_date, 'yyyy-MM') = um.month
            WHERE um.brand = 'STAR'
        ),
        event_agg AS (
            SELECT
                -- 1. Date
                date,

                -- 2. RLS Fields
                sales_id,
                p_ids,

                -- 3. Dimensions
                country,
                account_type,
                client_type,
                sales_org_id,
                sales_org_name,
                sales_name,
                cpa_id,
                cpa_name,
                master_ib_id,
                master_ib_name,
                ib_affid,
                ib_name,

                -- 4. Event Metrics
                SUM(CASE WHEN event = 'register' THEN 1 ELSE 0 END) AS register,
                SUM(CASE WHEN event = 'live' THEN 1 ELSE 0 END) AS live,
                SUM(CASE WHEN event = 'live_kyc' THEN 1 ELSE 0 END) AS live_kyc,
                SUM(CASE WHEN event = 'ftd' THEN 1 ELSE 0 END) AS ftd,
                SUM(CASE WHEN event = 'ftd' THEN COALESCE(event_amount, 0) ELSE 0 END) AS ftd_amount,
                SUM(CASE WHEN event = 'ftt' THEN 1 ELSE 0 END) AS ftt,
                SUM(CASE WHEN event = 'ftt' THEN COALESCE(event_amount, 0) ELSE 0 END) AS ftt_amount,

                -- 5. Trading Metrics (Null Placeholders)
                CAST(0 AS DECIMAL(30,8)) AS gross_deposit,
                CAST(0 AS DECIMAL(30,8)) AS withdrawal,
                CAST(0 AS DECIMAL(30,8)) AS net_deposit,
                CAST(0 AS DECIMAL(30,8)) AS rt_value,
                CAST(0 AS DECIMAL(30,8)) AS gross_deposit_rt,
                CAST(0 AS DECIMAL(30,8)) AS net_deposit_rt,
                CAST(0 AS INT)           AS t_dau,
                CAST(0 AS DOUBLE)        AS trading_volume,
                CAST(0 AS DECIMAL(30,8)) AS ib_rebate,
                CAST(0 AS DECIMAL(30,8)) AS cpa_rebate,
                CAST(0 AS DECIMAL(30,8)) AS gross_company_pnl,
                CAST(0 AS DECIMAL(30,8)) AS net_company_pnl,
                CAST(0 AS DECIMAL(30,8)) AS spread_revenue,
                CAST(0 AS DECIMAL(30,8)) AS commission_revenue,
                CAST(0 AS DECIMAL(30,8)) AS swaps_revenue,
                CAST(0 AS DECIMAL(30,8)) AS dividend_revenue,
                CAST(0 AS DECIMAL(30,8)) AS rollover_revenue,
                CAST(0 AS DECIMAL(30,8)) AS risk_free_revenue,
                CAST(0 AS DECIMAL(30,8)) AS risk_revenue,
                CAST(0 AS DECIMAL(30,8)) AS equity
            FROM event_attr
            WHERE date >= '2025-01-01' AND date < current_date()
            GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
        ),
        metrics_attr AS (
            SELECT
                t.date,
                COALESCE(lm.cpa_sales_id, lm.sales_id) AS sales_id,
                COALESCE(lm.cpa_sales_p_ids, lm.login_p_ids) AS p_ids,

                coalesce(u.country, 'Others') as country,
                lm.account_group_category_3 as account_type,
                lm.client_type,
                COALESCE(lm.cpa_sales_org_id, lm.sales_org_id) AS sales_org_id,
                COALESCE(lm.cpa_sales_org_name, lm.sales_org_name) AS sales_org_name,
                COALESCE(lm.cpa_sales_name, lm.sales_name) AS sales_name,
                lm.cpa_id,
                lm.cpa_name,
                lm.master_ib_id,
                lm.master_ib_name,
                lm.direct_ib_rebate_account AS ib_affid,
                lm.direct_ib_name AS ib_name,
                
                t.user_id,
                t.trading_volume,
                t.toc_trading_volume,
                t.gross_deposit,
                t.withdraw,
                t.net_deposit,
                t.daily_rebate_to_trade,
                t.ib_rebate,
                t.cpa_commission,
                t.gross_company_pnl,
                t.net_company_pnl,
                t.spread_revenue,
                t.commission_revenue,
                t.swaps_revenue,
                t.dividend_revenue,
                t.rollover_revenue,
                t.risk_free_revenue,
                t.risk_revenue,
                t.equity
            FROM platinum.gbis.dws_login_metrics_daily t
            LEFT JOIN platinum.gbis.dim_login_ownership_monthly lm
                ON t.login = lm.login
                AND t.server_id = lm.server_id
                AND date_format(t.date, 'yyyy-MM') = lm.month
            LEFT JOIN platinum.gbis.dim_user_base_daily_snapshot u
                ON t.user_id = u.user_id
                AND t.crm_server_id = u.crm_server_id
                AND u.client_type_id != 6
            WHERE lm.brand = 'STAR'
                AND t.date >= '2025-01-01'
                AND t.date < current_date()
        ),
        oz_agg AS (
            SELECT
                t.date,
                NULL AS sales_id,
                NULL AS p_ids,
                coalesce('Others') as country,
                'OZ' AS account_type,
                NULL AS client_type,
                NULL AS sales_org_id,
                'OZ' AS sales_org_name,
                'OZ' AS sales_name,
                NULL AS cpa_id,
                NULL AS cpa_name,
                NULL AS master_ib_id,
                NULL AS master_ib_name,
                NULL AS ib_affid,
                NULL AS ib_name,

                -- Event metrics
                0 AS register,
                0 AS live,
                0 AS live_kyc,
                0 AS ftd,
                0 AS ftd_amount,
                0 AS ftt,
                0 AS ftt_amount,

                -- Trading metrics
                SUM(gross_deposit) AS gross_deposit,
                SUM(withdraw) AS withdrawal,
                SUM(net_deposit) AS net_deposit,
                SUM(COALESCE(daily_rebate_to_trade, 0)) AS rt_value,
                SUM(gross_deposit + COALESCE(daily_rebate_to_trade, 0)) AS gross_deposit_rt,
                SUM(net_deposit + COALESCE(daily_rebate_to_trade, 0)) AS net_deposit_rt,
                0 AS t_dau, -- OZ has no concept of active users
                SUM(trading_volume) AS trading_volume,
                SUM(COALESCE(ib_rebate, 0)) AS ib_rebate,
                SUM(COALESCE(cpa_commission, 0)) AS cpa_rebate,
                SUM(gross_company_pnl) AS gross_company_pnl,
                SUM(net_company_pnl) AS net_company_pnl,
                SUM(spread_revenue) AS spread_revenue,
                SUM(commission_revenue) AS commission_revenue,
                SUM(swaps_revenue) AS swaps_revenue,
                SUM(dividend_revenue) AS dividend_revenue,
                SUM(rollover_revenue) AS rollover_revenue,
                SUM(risk_free_revenue) AS risk_free_revenue,
                SUM(risk_revenue) AS risk_revenue,
                SUM(equity) AS equity
            FROM platinum.gbis.dws_login_metrics_daily t
            WHERE t.brand = 'STAR_PRIME_OZ'
                AND t.date >= '2025-01-01'
                AND t.date < current_date()
            GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
        ),
        metrics_agg AS (
            SELECT
                date,
                sales_id,
                p_ids,
                country,
                account_type,
                client_type,
                sales_org_id,
                sales_org_name,
                sales_name,
                cpa_id,
                cpa_name,
                master_ib_id,
                master_ib_name,
                ib_affid,
                ib_name,

                -- Event metrics
                0 AS register,
                0 AS live,
                0 AS live_kyc,
                0 AS ftd,
                0 AS ftd_amount,
                0 AS ftt,
                0 AS ftt_amount,

                -- Trading metrics
                SUM(gross_deposit) AS gross_deposit,
                SUM(withdraw) AS withdrawal,
                SUM(net_deposit) AS net_deposit,
                SUM(daily_rebate_to_trade) AS rt_value,
                SUM(gross_deposit + daily_rebate_to_trade) AS gross_deposit_rt,
                SUM(net_deposit + daily_rebate_to_trade) AS net_deposit_rt,
                COUNT(DISTINCT CASE WHEN coalesce(trading_volume,0) - coalesce(toc_trading_volume,0) > 0 THEN user_id END) AS t_dau,
                SUM(trading_volume) AS trading_volume,
                SUM(ib_rebate) AS ib_rebate,
                SUM(cpa_commission) AS cpa_rebate,
                SUM(gross_company_pnl) AS gross_company_pnl,
                SUM(net_company_pnl) AS net_company_pnl,
                SUM(spread_revenue) AS spread_revenue,
                SUM(commission_revenue) AS commission_revenue,
                SUM(swaps_revenue) AS swaps_revenue,
                SUM(dividend_revenue) AS dividend_revenue,
                SUM(rollover_revenue) AS rollover_revenue,
                SUM(risk_free_revenue) AS risk_free_revenue,
                SUM(risk_revenue) AS risk_revenue,
                SUM(equity) AS equity
            FROM metrics_attr
            GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
        ),
        final as (
            SELECT * FROM event_agg
                UNION ALL
            SELECT * FROM metrics_agg
                UNION ALL
            SELECT * FROM oz_agg
        )
        SELECT 
            f.*, 

            -- Sales hierarchy
            o.level1                                                                       as level1,
            coalesce(o.level2, o.level1)                                                   as level2,
            coalesce(o.level3, o.level2, o.level1)                                         as level3,
            coalesce(o.level4, o.level3, o.level2, o.level1)                               as level4,
            coalesce(o.level5, o.level4, o.level3, o.level2, o.level1)                     as level5,
            coalesce(o.level6, o.level5, o.level4, o.level3, o.level2, o.level1)           as level6,
            coalesce(o.level7, o.level6, o.level5, o.level4, o.level3, o.level2, o.level1) as level7,

            -- RLS flags
            -- Sales ID
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '1673525') THEN 1 ELSE 0 END AS has_emma,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '1673524') THEN 1 ELSE 0 END AS has_harry,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '1673523') THEN 1 ELSE 0 END AS has_adam,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '1692035') THEN 1 ELSE 0 END AS has_jennie,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '1673522') THEN 1 ELSE 0 END AS has_luke,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '1677859') THEN 1 ELSE 0 END AS has_phil,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '1679350') THEN 1 ELSE 0 END AS has_john,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '2898500') THEN 1 ELSE 0 END AS has_jay,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '201746') THEN 1 ELSE 0 END AS has_mandy,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '2859349') THEN 1 ELSE 0 END AS has_moe,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '199162')
                OR array_contains(split(coalesce(p_ids, ''), ','), '2768657') THEN 1 ELSE 0 END AS has_jeff,
            CASE WHEN array_contains(split(coalesce(p_ids, ''), ','), '300749')
                OR array_contains(split(coalesce(p_ids, ''), ','), '2849241') THEN 1 ELSE 0 END AS has_yazan,

            -- Sales Org
            CASE WHEN 'CR Team' IN (o.level1, o.level2, o.level3, o.level4, o.level5, o.level6, o.level7) THEN 1 ELSE 0 END AS has_lewis,
            CASE WHEN 'VD Team' IN (o.level1, o.level2, o.level3, o.level4, o.level5, o.level6, o.level7) THEN 1 ELSE 0 END AS has_vd
        FROM final f
        LEFT JOIN org o on f.sales_org_id = o.id;
    """

def main():
    create_table(
        table_name=TARGET_TABLE,
        columns=cols,
        cluster_by="date",
        spark=spark
        )
    query = get_etl_query(DEFAULT_START_DATE)

    success = run_etl(
        query=query,
        table_name=TARGET_TABLE,
        start_date=DEFAULT_START_DATE,
        spark=spark
        )
    
    # if not success:
    #     dbutils.notebook.exit("FAILED")
    if success:
        optimize_table(
            table_name=TARGET_TABLE,
            spark=spark
        )

if __name__ == '__main__':
    main()
