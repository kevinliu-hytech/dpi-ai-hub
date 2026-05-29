from pyspark.sql import SparkSession
import sys

sys.path.append("/Workspace/github/pulse/")

from modules.datamart.utils import create_table, optimize_table, run_etl

TARGET_TABLE = "gbis.biz.dashboard_star_dim_users"

spark = SparkSession.builder \
    .appName("Star_Dim_Users") \
    .enableHiveSupport() \
    .getOrCreate()

print(f"✓ Spark session initialized")
print(f"✓ Target table: {TARGET_TABLE}")

# Define columns
cols = {
    "email": "STRING",
    "sales_id": "BIGINT"
}

def get_etl_query():
    return """
        WITH users AS (
            SELECT 'emma.wong@unicornfintech.com' AS email, 1673525 AS user_id
            UNION ALL
            SELECT 'harry.chin@unicornfintech.com', 1673524
            UNION ALL
            SELECT 'adam.ying@unicornfintech.com', 1673523
            UNION ALL
            SELECT 'jennie.kim@unicornfintech.com', 1692035
            UNION ALL
            SELECT 'ryan.wang@unicornfintech.com', 1673522
            UNION ALL
            SELECT 'eric.yu@unicornfintech.com', 1677859
            UNION ALL
            SELECT 'barry.tsang@unicornfintech.com', 1673525
            UNION ALL
            SELECT 'johi.yi@unicornfintech.com', 1679350
            UNION ALL
            SELECT 'jay.m@unicornfintech.com', 2898500
            UNION ALL
            SELECT 'mandy.tao@unicornfintech.com', 201746
            UNION ALL
            SELECT 'moe.padhani@unicornfintech.com', 2859349
            UNION ALL
            SELECT 'jeff.cheng@unicornfintech.com', 199162
            UNION ALL
            SELECT 'jeff.cheng@unicornfintech.com', 2768657
            UNION ALL
            SELECT 'yazan.abutafesh@unicornfintech.com', 300749
            UNION ALL
            SELECT 'yazan.abutafesh@unicornfintech.com', 2849241
        )
        SELECT * FROM users;
    """

def main():
    # Create table if not exists
    create_table(
        table_name=TARGET_TABLE,
        columns=cols,
        cluster_by=None,  # optional for small static table
        spark=spark
    )

    # Run ETL
    query = get_etl_query()
    success = run_etl(
        query=query,
        table_name=TARGET_TABLE,
        start_date=None,  # Not needed for static insert
        spark=spark
    )

    if success:
        optimize_table(
            table_name=TARGET_TABLE,
            spark=spark
        )

if __name__ == '__main__':
    main()

