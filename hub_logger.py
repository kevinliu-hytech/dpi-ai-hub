"""
Hub Observability Logger — Structured JSON logs for every hub request.
Logs: route decision, SQL/API calls, data quality, chart decision, latency.
Output: logs/hub_requests.jsonl (one JSON per line, append-only)
"""
import os
import json
import time
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'hub_requests.jsonl')

os.makedirs(LOG_DIR, exist_ok=True)


class HubLogger:
    def __init__(self):
        self.log_file = LOG_FILE

    def log_request(self, entry):
        entry['logged_at'] = datetime.utcnow().isoformat() + 'Z'
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
        except Exception as e:
            print(f'[HubLogger] Write error: {e}')

    def start(self, question, user_email=None):
        return RequestLog(self, question, user_email)


class RequestLog:
    def __init__(self, logger, question, user_email=None):
        self.logger = logger
        self.start_time = time.time()
        self.entry = {
            'question': question,
            'user': user_email,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }

    def set_route(self, agent, confidence=None):
        self.entry['route'] = agent
        if confidence is not None:
            self.entry['route_confidence'] = confidence

    def set_response(self, response, agent_type):
        elapsed = round(time.time() - self.start_time, 2)
        self.entry['latency_s'] = elapsed
        self.entry['agent_type'] = agent_type

        # SQL (internal)
        sql = response.get('sql')
        if sql:
            if isinstance(sql, list):
                self.entry['sql'] = sql
                self.entry['sql_tables'] = self._extract_tables(sql)
            else:
                self.entry['sql'] = [sql]
                self.entry['sql_tables'] = self._extract_tables([sql])

        # Data
        data = response.get('data')
        if data:
            self.entry['data_rows'] = len(data)
            if data:
                self.entry['data_columns'] = list(data[0].keys()) if isinstance(data[0], dict) else []
        else:
            self.entry['data_rows'] = 0

        # Chart
        chart = response.get('chart')
        if chart:
            if isinstance(chart, list) and chart:
                c = chart[0]
                self.entry['chart'] = {
                    'type': c.get('type'),
                    'x': c.get('x'),
                    'y': c.get('y'),
                    'title': c.get('title', '')[:80]
                }
            else:
                self.entry['chart'] = None
        else:
            self.entry['chart'] = None

        # Answer summary
        answer = response.get('answer', '')
        self.entry['answer_length'] = len(answer)
        self.entry['answer_preview'] = answer[:150]

        # Suggestions
        self.entry['suggestions'] = response.get('suggestions')

        # Error
        if 'error' in response:
            self.entry['error'] = response['error']

    def set_error(self, error):
        elapsed = round(time.time() - self.start_time, 2)
        self.entry['latency_s'] = elapsed
        self.entry['error'] = str(error)

    def save(self):
        self.logger.log_request(self.entry)

    def _extract_tables(self, sql_list):
        tables = set()
        for sql in sql_list:
            if not sql:
                continue
            sql_lower = sql.lower()
            import re
            matches = re.findall(r'from\s+([\w.]+)', sql_lower)
            matches += re.findall(r'join\s+([\w.]+)', sql_lower)
            tables.update(matches)
        return list(tables)
