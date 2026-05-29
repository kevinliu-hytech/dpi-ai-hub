---
category: getting_started
description: Example query template - copy and modify this
tables: [your_table_name]
complexity: simple
---

# Query Name: Example Starter Query

## Description
Describe what this query does and why you use it.

## SQL Query
```sql
SELECT 
    column1,
    column2,
    COUNT(*) as total
FROM your_table_name
WHERE date_column >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
GROUP BY column1, column2
ORDER BY total DESC
LIMIT 10;
```

## Sample Natural Language Questions
- "Show me..."
- "What is the..."
- "How many..."

## Expected Output Columns
- column1: Description of what this column contains
- column2: Description of what this column contains
- total: Count of records

## Business Context (Optional)
Explain any special business rules, calculations, or important context about this query.

## Related Queries (Optional)
- Link to other similar queries
- Variations of this query

---

**Instructions:** 
1. Copy this file
2. Rename it to describe your query (e.g., `sales_monthly_revenue.md`)
3. Fill in your actual query and details
4. Save it in the `examples/` folder
