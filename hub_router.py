"""
Hub Router — LLM-based intent classifier.
Routes questions to internal data agent or external data agent (placeholder).
Uses Haiku for fast, cheap classification.
"""
import json
import boto3
import os


class HubRouter:
    def __init__(self):
        session = boto3.Session(
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        self.bedrock = session.client('bedrock-runtime')
        self.model_id = 'us.anthropic.claude-3-5-haiku-20241022-v1:0'
        self.prompt_template = self._load_prompt()

    def _load_prompt(self):
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'router.md')
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r') as f:
                return f.read()
        return 'Classify: "{text}". Output JSON: {{"agent": "internal_data", "confidence": 0.8}}'

    def route(self, text):
        """Classify user intent → which agent to use."""
        prompt = self.prompt_template.replace('{text}', text)

        try:
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 60,
                    'messages': [{'role': 'user', 'content': prompt}]
                })
            )
            result = json.loads(response['body'].read())
            text_out = result['content'][0]['text'].strip()

            try:
                parsed = json.loads(text_out)
                return parsed
            except json.JSONDecodeError:
                import re
                match = re.search(r'\{.*\}', text_out, re.DOTALL)
                if match:
                    return json.loads(match.group())
        except Exception as e:
            print(f'[HubRouter] Error: {e}')

        return {'agent': 'internal_data', 'confidence': 0.8}
