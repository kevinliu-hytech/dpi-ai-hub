# Deployment

## Production Environment

| Item | Value |
|------|-------|
| Server | EC2 `kevin-ec2-new` (18.136.250.8) |
| App path | `/home/ec2-user/gbis-analysis/` |
| Python | `/home/ec2-user/gbis-analysis/venv/bin/python3` |
| Process | Gunicorn (2 workers, port 5000, 300s timeout) |
| Proxy | Nginx container → port 5000 |
| URLs | `/gbis-ai-hub/hub` (AI Hub), `/gbis-analysis/chat` (Exec Chat) |

## Deploy a Code Change

```bash
# Upload file(s)
scp path/to/file kevin-ec2-new:/home/ec2-user/gbis-analysis/path/to/file

# Upload a directory
scp -r prompts/ kevin-ec2-new:/home/ec2-user/gbis-analysis/prompts/

# Reload (zero-downtime)
ssh kevin-ec2-new "kill -HUP \$(pgrep -f 'gunicorn.*wsgi:app' -o)"
```

Workers respawn with new code. Master PID stays the same.

## Environment Variables

Managed in `/home/ec2-user/gbis-analysis/.env` on EC2. Key variables:

```
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
DATABRICKS_SERVER_HOSTNAME=...
DATABRICKS_HTTP_PATH=...
DATABRICKS_ACCESS_TOKEN=...
COMPETITOR_API_BASE_URL=http://localhost:8764
COMPETITOR_API_KEY=...
```

## Logs

- Application logs: `logs/hub_requests.jsonl` (structured, append-only)
- Gunicorn output: stdout/stderr of gunicorn process

View logs:
```bash
ssh kevin-ec2-new "tail -50 /home/ec2-user/gbis-analysis/logs/hub_requests.jsonl"
```

## Troubleshooting

**Workers not responding after reload:**
```bash
ssh kevin-ec2-new "pgrep -fa 'gunicorn.*wsgi:app'"
# Should show 1 master + 2 workers
```

**Check app can import cleanly:**
```bash
ssh kevin-ec2-new "cd /home/ec2-user/gbis-analysis && venv/bin/python -c 'import app; print(\"OK\")'"
```

**Full restart (last resort):**
```bash
ssh kevin-ec2-new "pkill -f 'gunicorn.*wsgi:app' && sleep 2 && cd /home/ec2-user/gbis-analysis && source venv/bin/activate && nohup gunicorn --workers 2 --bind 0.0.0.0:5000 --timeout 300 wsgi:app > gunicorn.log 2>&1 &"
```
