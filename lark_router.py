"""
LLM-based intent router for Lark Bot.
Routes user messages to the appropriate agent.
"""
import json
import boto3
from config import Config


AGENT_DEFINITIONS = [
    {
        'name': 'internal_data',
        'description': '内部数据分析：GBIS业务指标查询、品牌业绩、NRFR/NDM/RFR/TDAU/FTD、目标完成度、趋势分析等',
        'keywords': ['数据', '品牌', '业绩', '完成度', '趋势', '排名', '对比', '分析']
    },
    {
        'name': 'external_data',
        'description': '外部数据分析：市场数据、竞品分析、行业趋势、外部报告等',
        'keywords': ['市场', '竞品', '行业', '外部']
    }
]


class LarkRouter:
    def __init__(self):
        self.bedrock = boto3.client(
            'bedrock-runtime',
            region_name=Config.AWS_REGION if hasattr(Config, 'AWS_REGION') else 'ap-southeast-1'
        )
        self.model_id = 'us.anthropic.claude-haiku-4-5-20251001'

    def route(self, text):
        """Route a message to the appropriate agent using LLM."""
        # Fast path: if only one agent is active, skip LLM
        active_agents = [a for a in AGENT_DEFINITIONS if a['name'] == 'internal_data']
        if len(AGENT_DEFINITIONS) <= 1 or self._only_internal_active():
            return {'agent': 'internal_data', 'confidence': 1.0}

        try:
            return self._llm_route(text)
        except Exception as e:
            print(f'[Router] LLM routing failed: {e}, falling back to internal_data')
            return {'agent': 'internal_data', 'confidence': 0.5}

    def _only_internal_active(self):
        """Check if only internal_data agent is implemented."""
        # For now, external_data is not yet implemented
        return True

    def _llm_route(self, text):
        """Use LLM to classify intent."""
        agents_desc = '\n'.join([f"- {a['name']}: {a['description']}" for a in AGENT_DEFINITIONS])

        prompt = f"""你是一个意图分类器。根据用户消息，判断应该路由到哪个Agent。

可用Agent：
{agents_desc}

用户消息："{text}"

只输出JSON：{{"agent": "agent_name", "confidence": 0.0-1.0}}"""

        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 100,
                'messages': [{'role': 'user', 'content': prompt}]
            })
        )

        result = json.loads(response['body'].read())
        text_out = result['content'][0]['text'].strip()

        # Parse JSON from response
        try:
            parsed = json.loads(text_out)
            return parsed
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', text_out, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {'agent': 'internal_data', 'confidence': 0.5}
