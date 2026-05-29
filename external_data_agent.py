"""
External Data Agent — Competitor Intelligence via REST API.
Routes: Hub → external_data → this module.
Pattern: Plan API calls (Haiku) → Execute → Synthesize response (Opus)
"""
import os
import json
import re
import requests
import boto3


class ExternalDataAgent:
    def __init__(self):
        self.api_base = os.getenv('COMPETITOR_API_BASE_URL', 'http://18.136.250.8/competitor-api')
        self.api_key = os.getenv('COMPETITOR_API_KEY', 'pN1B8cGTIyGR8Zoi-hgUQl20rCmzHqpYeGdx2tl3bTE')
        self.bedrock = self._init_bedrock()
        self.planner_model = 'us.anthropic.claude-3-5-haiku-20241022-v1:0'
        self.analyst_model = 'us.anthropic.claude-opus-4-7'
        self.prompts = self._load_prompts()
        self.broker_list = self._load_broker_list()

    def _load_prompts(self):
        prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        prompts = {}
        for name in ['external_planner', 'external_analyst_en', 'external_analyst_zh', 'chart_decision']:
            path = os.path.join(prompts_dir, f'{name}.md')
            if os.path.exists(path):
                with open(path, 'r') as f:
                    prompts[name] = f.read()
        return prompts

    def _init_bedrock(self):
        session = boto3.Session(
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        return session.client('bedrock-runtime')

    def _load_broker_list(self):
        try:
            resp = requests.get(
                f'{self.api_base}/api/v1/social/brokers',
                headers={'X-API-Key': self.api_key},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                return [b['broker_name'] for b in data.get('data', [])]
        except Exception as e:
            print(f'[ExternalAgent] Failed to load broker list: {e}')
        return []

    def _call_llm(self, model_id, system_prompt, messages, max_tokens=2000):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages
        }
        response = self.bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body)
        )
        result = json.loads(response['body'].read())
        return result['content'][0]['text']

    def _api_get(self, endpoint, params=None):
        try:
            resp = requests.get(
                f'{self.api_base}{endpoint}',
                headers={'X-API-Key': self.api_key},
                params=params,
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json()
            return {'error': f'HTTP {resp.status_code}: {resp.text[:200]}'}
        except requests.Timeout:
            return {'error': 'API request timeout'}
        except Exception as e:
            return {'error': str(e)}

    def chat(self, message, history=None):
        is_en = self._detect_english(message)

        if not self.api_key:
            msg = 'Competitor API not configured. Please contact admin.' if is_en else '竞品数据API未配置，请联系管理员设置COMPETITOR_API_KEY。'
            return {
                'answer': msg,
                'data': None, 'chart': None, 'suggestions': None
            }

        plan = self._plan_api_calls(message)
        api_results = self._execute_api_calls(plan)

        if not api_results or all('error' in r for r in api_results):
            error_msg = api_results[0].get('error', 'Unknown error') if api_results else ('Cannot connect to competitor data service' if is_en else '无法连接竞品数据服务')
            prefix = 'Competitor data query failed: ' if is_en else '竞品数据查询失败：'
            return {
                'answer': f'{prefix}{error_msg}',
                'data': None, 'chart': None,
                'suggestions': None
            }

        response = self._synthesize_response(message, api_results, history)

        chart_decision = self._decide_chart(message, api_results, is_en)
        if chart_decision and chart_decision.get('show'):
            chart_data = self._extract_chart_data(api_results, is_en)
            chart = self._build_chart_from_decision(chart_data, chart_decision, is_en) if chart_data else None
        else:
            chart_data = None
            chart = None

        return {
            'answer': response['answer'],
            'data': chart_data,
            'chart': chart,
            'suggestions': response.get('suggestions')
        }

    def _plan_api_calls(self, message):
        broker_list_str = ', '.join(self.broker_list) if self.broker_list else '(not loaded)'
        template = self.prompts.get('external_planner', '')
        system_prompt = template.replace('{broker_list}', broker_list_str)

        try:
            result = self._call_llm(
                self.planner_model, system_prompt,
                [{'role': 'user', 'content': message}],
                max_tokens=400
            )
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f'[ExternalAgent] Plan error: {e}')

        return {'calls': [{'endpoint': '/api/v1/social/brokers', 'params': {}}]}

    def _execute_api_calls(self, plan):
        results = []
        calls = plan.get('calls', [])
        for call in calls[:3]:
            endpoint = call.get('endpoint', '')
            params = call.get('params', {})
            result = self._api_get(endpoint, params if params else None)
            result['_endpoint'] = endpoint
            results.append(result)
        return results

    def _decide_chart(self, message, api_results, is_en=False):
        data_summary_parts = []
        for r in api_results:
            if 'error' in r:
                continue
            endpoint = r.get('_endpoint', '')
            clean = {k: v for k, v in r.items() if k != '_endpoint'}
            data_summary_parts.append(f"Endpoint: {endpoint}\nFields: {list(clean.keys())[:20]}\nSample: {json.dumps(clean, ensure_ascii=False, default=str)[:500]}")

        data_summary = '\n\n'.join(data_summary_parts)

        system_prompt = self.prompts.get('chart_decision', 'Output: {"show": false}')

        try:
            result = self._call_llm(
                self.planner_model, system_prompt,
                [{'role': 'user', 'content': f"Question: {message}\n\nAPI Data:\n{data_summary}"}],
                max_tokens=200
            )
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f'[ExternalAgent] Chart decision error: {e}')
        return {'show': False}

    def _build_chart_from_decision(self, data, decision, is_en=False):
        if not data or len(data) < 2:
            return None

        chart_type = decision.get('type', 'bar')
        metric = decision.get('metric', '')
        title = decision.get('title', '')

        columns = [k for k in data[0].keys() if not k.startswith('_')]
        numeric_cols = [c for c in columns if isinstance(data[0].get(c), (int, float))]
        non_numeric_cols = [c for c in columns if not isinstance(data[0].get(c), (int, float))]

        if metric not in numeric_cols:
            metric = numeric_cols[0] if numeric_cols else None
        if not metric:
            return None

        date_cols = [c for c in non_numeric_cols if any(k in c.lower() for k in ('date', 'time', 'month', 'collection'))]

        if chart_type == 'line' and date_cols:
            x_col = date_cols[0]
            color_col = next((c for c in non_numeric_cols if c != x_col), None)
            return [{'type': 'line', 'title': title, 'x': x_col, 'y': metric, 'color': color_col}]

        if chart_type == 'pie' and non_numeric_cols:
            x_col = non_numeric_cols[0]
            return [{'type': 'pie', 'title': title, 'x': x_col, 'y': metric}]

        if non_numeric_cols:
            x_col = non_numeric_cols[0]
            color_col = next((c for c in non_numeric_cols if c != x_col), None)
            return [{'type': 'bar', 'title': title, 'x': x_col, 'y': metric, 'color': color_col}]

        return None

    def _extract_chart_data(self, api_results, is_en=False):
        # Priority 1: Summary data (single broker cross-platform comparison)
        summaries = []
        for result in api_results:
            if 'error' in result:
                continue
            endpoint = result.get('_endpoint', '')
            if '/summary' in endpoint and 'platforms' in result:
                broker = result.get('broker_name', '')
                for platform, metrics in result['platforms'].items():
                    followers = metrics.get('followers', 0) or 0
                    if followers > 0:
                        summaries.append({
                            'broker': broker,
                            'platform': platform,
                            'followers': followers
                        })
        if summaries:
            return summaries

        # Priority 2: Leaderboard (cross-broker ranking)
        for result in api_results:
            if 'error' in result:
                continue
            endpoint = result.get('_endpoint', '')
            if '/leaderboard' in endpoint and 'data' in result:
                platform = result.get('meta', {}).get('platform', '')
                metric = result.get('meta', {}).get('metric', 'followers')
                data = result['data']
                for row in data:
                    row.pop('rank', None)
                if platform:
                    title = f'{platform} {metric} Ranking' if is_en else f'{platform} {metric}排名'
                    for row in data:
                        row['_chart_title'] = title
                return data

        # Priority 3: Metrics (time series)
        for result in api_results:
            if 'error' in result:
                continue
            endpoint = result.get('_endpoint', '')
            if '/metrics' in endpoint and 'data' in result and len(result['data']) > 0:
                return result['data']

        # Priority 4: Brokers list
        for result in api_results:
            if 'error' in result:
                continue
            endpoint = result.get('_endpoint', '')
            if '/brokers' in endpoint and 'data' in result and '/summary' not in endpoint:
                rows = []
                for b in result['data']:
                    total_followers = sum(p.get('followers', 0) or 0 for p in b.get('platforms', []))
                    if total_followers > 0:
                        rows.append({'broker': b['broker_name'], 'total_followers': total_followers})
                if rows:
                    rows.sort(key=lambda x: x['total_followers'], reverse=True)
                    return rows[:15]
        return None

    def _synthesize_response(self, message, api_results, history=None):
        context_parts = []
        for r in api_results:
            if 'error' in r:
                continue
            endpoint = r.get('_endpoint', '')
            clean = {k: v for k, v in r.items() if k != '_endpoint'}
            context_parts.append(f"API: {endpoint}\n{json.dumps(clean, ensure_ascii=False, default=str)[:3000]}")

        api_context = '\n\n'.join(context_parts)

        is_english = self._detect_english(message)

        if is_english:
            system_prompt = self.prompts.get('external_analyst_en', 'Answer in English based on the data.')
        else:
            system_prompt = self.prompts.get('external_analyst_zh', '基于数据用中文回答。')

        messages = []
        if history:
            for h in history[-6:]:
                messages.append({'role': h['role'], 'content': h['content']})

        instruction = "Provide a concise English analysis with key data points and follow-up suggestions." if is_english else "请给出简洁的中文分析回答，包含关键数据要点和跟进建议。"
        messages.append({
            'role': 'user',
            'content': f"""{message}

API Data:
{api_context}

{instruction}"""
        })

        try:
            result = self._call_llm(self.analyst_model, system_prompt, messages)
            suggestions = self._extract_suggestions(result)
            clean = re.sub(r'`{1,3}\s*suggestions\s*\n?.*?\n?`{1,3}', '', result, flags=re.DOTALL).strip()
            return {'answer': clean, 'suggestions': suggestions}
        except Exception as e:
            return {'answer': f'Analysis failed: {str(e)}', 'suggestions': None}

    def _detect_english(self, text):
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        return ascii_chars / max(len(text), 1) > 0.7

    def _extract_suggestions(self, text):
        match = re.search(r'`{1,3}\s*suggestions?\s*\n?(.*?)\n?`{1,3}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        match2 = re.search(r'suggestions?\s*[:\n]\s*(\[.*?\])', text, re.DOTALL)
        if match2:
            try:
                return json.loads(match2.group(1).strip())
            except json.JSONDecodeError:
                pass
        return None
