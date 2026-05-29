from pyspark.sql import SparkSession
from datetime import datetime, timedelta
import sys

sys.path.append("/Workspace/github/pulse/")

from modules.datamart.utils import create_table, optimize_table, validate_source_data, run_etl

TARGET_TABLE = "gbis.biz.dashboard_star_sales_metrics_daily"
DEFAULT_START_DATE = "2025-01-01"
spark = SparkSession.builder \
    .appName("Star_Sales_Metrics_Daily") \
    .enableHiveSupport() \
    .getOrCreate()

print(f"✓ Spark session initialized")
print(f"✓ Target table: {TARGET_TABLE}")


cols = {
    # Date and core dimensions
    "date": "DATE",
    "country": "STRING",
    "client_type": "STRING",
    "sales_org_name": "STRING",
    "account_type": "STRING",

    # Sales
    "sales_id": "BIGINT",
    "sales_name": "STRING",
    "p_ids": "STRING",
    "ib_affid": "BIGINT",
    "cpa_id": "BIGINT",

    # Sales hierarchy
    "level1": "STRING",
    "level2": "STRING",
    "level3": "STRING",
    "level4": "STRING",
    "level5": "STRING",
    "level6": "STRING",
    "level7": "STRING",

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

        SELECT
            -- Dimensions
            f.date,
            f.country,
            f.client_type,
            f.sales_org_name,
            f.account_type,
            f.sales_id,
            f.sales_name,
            f.p_ids,
            f.ib_affid,
            f.cpa_id,

            -- Sales hierarchy
            f.level1,
            f.level2,
            f.level3,
            f.level4,
            f.level5,
            f.level6,
            f.level7,
            
            -- RLS fields
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

            -- Metrics
            SUM(register),
            SUM(live),
            SUM(live_kyc),
            SUM(ftd),
            SUM(ftd_amount),
            SUM(ftt),
            SUM(ftt_amount),
            SUM(gross_deposit),
            SUM(withdrawal),
            SUM(net_deposit),
            SUM(rt_value),
            SUM(gross_deposit_rt),
            SUM(net_deposit_rt),
            SUM(t_dau) as t_dau, 
            SUM(trading_volume),
            SUM(ib_rebate),
            SUM(cpa_rebate),
            SUM(gross_company_pnl),
            SUM(net_company_pnl),
            SUM(spread_revenue),
            SUM(commission_revenue),
            SUM(swaps_revenue),
            SUM(dividend_revenue),
            SUM(rollover_revenue),
            SUM(risk_free_revenue),
            SUM(risk_revenue),
            SUM(equity)
        FROM gbis.biz.dashboard_star_fact_daily_kpi f
        GROUP BY 
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31;
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
