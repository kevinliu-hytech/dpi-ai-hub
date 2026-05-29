from pyspark.sql import SparkSession
from datetime import datetime, timedelta
import sys

sys.path.append("/Workspace/github/pulse/")

from modules.datamart.utils import create_table, optimize_table, validate_source_data, run_etl

TARGET_TABLE = "gbis.biz.dashboard_star_ib_metrics_daily"
DEFAULT_START_DATE = "2025-01-01"
spark = SparkSession.builder \
    .appName("Star_Sales_Metrics_Daily") \
    .enableHiveSupport() \
    .getOrCreate()

print(f"✓ Spark session initialized")
print(f"✓ Target table: {TARGET_TABLE}")

cols = {
    # Core dimensions
    "date": "DATE",
    "country": "STRING",
    "client_type": "STRING",
    "master_ib_id": "BIGINT",
    "master_ib_name": "STRING",
    "ib_affid": "BIGINT",
    "ib_name": "STRING",
    "sales_org_name": "STRING",
    "sales_org_id": "BIGINT",

    # Sales
    "sales_id": "BIGINT",
    "sales_name": "STRING",
    "p_ids": "STRING",

    # IB hierarchy info
    "path": "STRING",
    "name_path": "STRING",

    # RLS required fields
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
    "has_vd": "BOOLEAN",
        
    # KPIs
    "register": "BIGINT",
    "live": "BIGINT",
    "live_kyc": "BIGINT",
    "ftd": "BIGINT",
    "ftd_amount": "DOUBLE",
    "ftt": "BIGINT",
    "ftt_amount": "DOUBLE",
    "gross_deposit": "DOUBLE",
    "withdrawal": "DOUBLE",
    "net_deposit": "DOUBLE",
    "rt_value": "DOUBLE",
    "gross_deposit_rt": "DOUBLE",
    "net_deposit_rt": "DOUBLE",
    "t_dau": "BIGINT",
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
    "equity": "DOUBLE"
}


def get_etl_query(start_date: str = DEFAULT_START_DATE):
    return f"""
        WITH ib as (select distinct date_trunc('month', `date`) as date_month,
            first_value(`date`)
                        over (partition by date_trunc('month', `date`), login order by `date` desc) as last_date,
            first_value(login)
                        over (partition by date_trunc('month', `date`), login order by `date` desc) as login,
            first_value(rebate_account_chain)
                        over (partition by date_trunc('month', `date`), login order by `date` desc) as path,
            first_value(name_chain)
                        over (partition by date_trunc('month', `date`), login order by `date` desc) as name_path
        from gbis.prod.dim_ib_chain_daily
        where crm_server_id = 1010)
        SELECT
            -- 1. Dimensions
            f.date,
            f.country,
            f.client_type,
            f.master_ib_id,
            f.master_ib_name,
            f.ib_affid,
            f.ib_name,
            f.sales_org_name,
            f.sales_org_id,
            f.sales_id,
            f.sales_name,
            f.p_ids,
            i.path,
            i.name_path,

            -- 2. RLS flags
            f.has_emma,
            f.has_harry,
            f.has_adam,
            f.has_jennie,
            f.has_luke,
            f.has_phil,
            f.has_john,
            f.has_jay,
            f.has_mandy,
            f.has_moe,
            f.has_jeff,
            f.has_yazan,
            f.has_lewis,
            f.has_vd,

            -- 3. Aggregated KPIs
            SUM(f.register) AS register,
            SUM(f.live) AS live,
            SUM(f.live_kyc) AS live_kyc,
            SUM(f.ftd) AS ftd,
            SUM(f.ftd_amount) AS ftd_amount,
            SUM(f.ftt) AS ftt,
            SUM(f.ftt_amount) AS ftt_amount,
            SUM(f.gross_deposit) AS gross_deposit,
            SUM(f.withdrawal) AS withdrawal,
            SUM(f.net_deposit) AS net_deposit,
            SUM(f.rt_value) AS rt_value,
            SUM(f.gross_deposit_rt) AS gross_deposit_rt,
            SUM(f.net_deposit_rt) AS net_deposit_rt,
            SUM(f.t_dau) AS t_dau,
            SUM(f.trading_volume) AS trading_volume,
            SUM(f.ib_rebate) AS ib_rebate,
            SUM(f.cpa_rebate) AS cpa_rebate,
            SUM(f.gross_company_pnl) AS gross_company_pnl,
            SUM(f.net_company_pnl) AS net_company_pnl,
            SUM(f.spread_revenue) AS spread_revenue,
            SUM(f.commission_revenue) AS commission_revenue,
            SUM(f.swaps_revenue) AS swaps_revenue,
            SUM(f.dividend_revenue) AS dividend_revenue,
            SUM(f.rollover_revenue) AS rollover_revenue,
            SUM(f.risk_free_revenue) AS risk_free_revenue,
            SUM(f.risk_revenue) AS risk_revenue,
            SUM(f.equity) AS equity
        FROM gbis.biz.dashboard_star_fact_daily_kpi f
        LEFT JOIN ib i ON 
            f.ib_affid = i.login
            and date_format(f.date, 'yyyy-MM') = i.date_month
        WHERE f.client_type IN ('IB', 'Hybrid')
        GROUP BY
            -- Dimensions
            f.date, 
            f.country, 
            f.client_type,
            f.master_ib_id,
            f.master_ib_name,
            f.ib_affid,
            f.ib_name,
            f.sales_org_name, 
            f.sales_org_id, 
            f.sales_id, 
            f.sales_name, 
            f.p_ids, 
            i.path, 
            i.name_path,
            
            -- RLS flags
            f.has_emma,
            f.has_harry,
            f.has_adam,
            f.has_jennie,
            f.has_luke,
            f.has_phil,
            f.has_john,
            f.has_jay,
            f.has_mandy,
            f.has_moe,
            f.has_jeff,
            f.has_yazan,
            f.has_lewis,
            f.has_vd;
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

