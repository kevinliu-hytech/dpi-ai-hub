"""
GS brand — FTD count for the last 30 days.

Usage:
    cd ~/metrics-dashboard
    source venv/bin/activate
    python queries/gs_ftd_last30days.py
"""
import os
from dotenv import load_dotenv
from databricks import sql

load_dotenv()

SQL_SUMMARY = """
SELECT
    SUM(ftd_count)        AS ftd_total,
    MIN(date)             AS from_date,
    MAX(date)             AS to_date,
    COUNT(DISTINCT date)  AS days_covered
FROM gbis.biz.ads_kpi_summary_daily
WHERE brand = 'GS'
  AND date >= DATE_SUB(CURRENT_DATE(), 30)
  AND date <  CURRENT_DATE()
"""

SQL_CROSSCHECK = """
SELECT SUM(ftd) AS ftd_total
FROM gbis.biz.dashboard_gs_sales_metrics_daily
WHERE date >= DATE_SUB(CURRENT_DATE(), 30)
  AND date <  CURRENT_DATE()
"""

SQL_DAILY = """
SELECT date, SUM(ftd_count) AS ftd
FROM gbis.biz.ads_kpi_summary_daily
WHERE brand = 'GS'
  AND date >= DATE_SUB(CURRENT_DATE(), 30)
  AND date <  CURRENT_DATE()
GROUP BY date
ORDER BY date
"""


def main() -> None:
    with sql.connect(
        server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_ACCESS_TOKEN"],
    ) as conn, conn.cursor() as cur:
        cur.execute(SQL_SUMMARY)
        total, d_from, d_to, days = cur.fetchone()
        print(f"GS FTD  {d_from} → {d_to}  ({days} days)")
        print(f"Total:  {total:,}\n")

        cur.execute(SQL_CROSSCHECK)
        (cross,) = cur.fetchone()
        match = "OK" if cross == total else "MISMATCH"
        print(f"Cross-check (dashboard_gs_sales_metrics_daily): {cross:,}  [{match}]\n")

        cur.execute(SQL_DAILY)
        print("Daily breakdown:")
        for d, ftd in cur.fetchall():
            print(f"  {d}  {ftd:>5,}")


if __name__ == "__main__":
    main()
