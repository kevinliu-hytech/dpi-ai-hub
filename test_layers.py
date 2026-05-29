from dotenv import load_dotenv
load_dotenv()
from chat_engine import ChatEngine
engine = ChatEngine()

# Test Layer A: detect bad column name
print("=== Layer A: SQL Validation ===")
is_valid, fixed = engine._validate_sql(
    "SELECT date, brand, nrfr_amount FROM gbis.biz.ads_kpi_summary_daily WHERE brand = 'STAR'",
    "STAR的NRFR"
)
print(f"Bad column test - valid: {is_valid}, has fix: {fixed is not None}")
if fixed:
    print(f"Fixed SQL: {fixed[:100]}")

# Test Layer A: correct SQL
is_valid2, fixed2 = engine._validate_sql(
    "SELECT date, brand, SUM(risk_free_revenue) - SUM(front_end_ecost) AS nrfr FROM gbis.biz.ads_kpi_summary_daily WHERE brand = 'STAR' AND date >= '2026-05-01' GROUP BY 1,2",
    "STAR 5月NRFR"
)
print(f"Good SQL test - valid: {is_valid2}, has fix: {fixed2 is not None}")

# Test Layer B: suspicious data (MM = 0)
print("\n=== Layer B: Data Validation ===")
test_data = [
    {"brand": "VT", "nrfr": 50000000},
    {"brand": "GS", "nrfr": 80000000},
    {"brand": "MM", "nrfr": 0},
]
valid, issue = engine._validate_data(test_data, "各品牌NRFR对比", "SELECT brand, SUM(risk_free_revenue - front_end_ecost) AS nrfr FROM gbis.biz.ads_kpi_summary_daily GROUP BY brand")
print(f"Suspicious data test - valid: {valid}, issue: {issue}")
