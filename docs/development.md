# Development Guide

## Adding / Editing Prompts

All LLM prompts live in `prompts/*.md`. They are loaded at app startup.

- Use `{placeholder}` for variable substitution (replaced via `.replace()`, never `.format()`)
- After editing, deploy and reload — no code changes needed

| File | Used by | Variables |
|------|---------|-----------|
| `router.md` | Hub Router | `{text}` |
| `internal_chart_decision.md` | Chat Engine (chart) | — (passed as system prompt) |
| `chart_decision.md` | External Agent (chart) | — |
| `external_planner.md` | External Agent (API planning) | `{broker_list}` |
| `external_analyst_en.md` | External Agent (English response) | — |
| `external_analyst_zh.md` | External Agent (Chinese response) | — |

## Knowledge Base

`kb/gbis_knowledge_base.md` contains domain rules for SQL generation:
- Table schemas and column descriptions
- Business logic (e.g., Gold vs 247 Gold filtering)
- Date function mappings (DAYOFWEEK conventions)

Add entries when the model consistently gets a domain-specific query wrong.

## Few-Shot SQL Examples

`queries/examples/*.md` — one file per table or topic. Format:

```markdown
# Table: schema.table_name

## Question: ...
```sql
SELECT ...
```
```

Priority loading: files prefixed with `brand_` load first.

## Evaluation

`eval/eval_cases.json` — test cases covering routing, SQL accuracy, and chart decisions.

Run on EC2 (requires Databricks + Bedrock access):
```bash
ssh kevin-ec2-new "cd /home/ec2-user/gbis-analysis && venv/bin/python eval/run_eval.py"
```

### Adding a Test Case

```json
{
  "id": "unique_id",
  "question": "user question",
  "expected_route": "internal_data",
  "expected_sql_contains": ["table_name", "WHERE clause fragment"],
  "expected_chart": "line",
  "context": []
}
```

## Observability

Every hub request logs to `logs/hub_requests.jsonl`:
- Question, route, confidence
- SQL generated, tables accessed
- Response latency, data row count
- Chart config, answer preview
- User feedback (good/bad)

## Frontend

Both `hub.html` and `chat.html` share `static/chat_app.js` and `static/chat_style.css`.

**Important:** When modifying templates or JS/CSS, always update both hub and chat versions and bump the `?v=N` cache-buster query parameter.
