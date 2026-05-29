"""
External News Agent — Industry news & competitor intelligence via REST API.
Endpoint: http://18.136.250.8/bi-digest-chatbot/ask
"""
import os
import requests


class ExternalNewsAgent:
    def __init__(self):
        self.api_url = os.getenv('NEWS_AGENT_URL', 'http://localhost:5022/bi-digest-chatbot/ask')

    def chat(self, message, history=None):
        payload = {'question': message}

        if history:
            conversation_context = []
            for h in history[-6:]:
                conversation_context.append({'role': h['role'], 'content': h['content']})
            if conversation_context:
                payload['conversation_context'] = conversation_context

        try:
            resp = requests.post(self.api_url, json=payload, timeout=60)
            if resp.status_code != 200:
                return {
                    'answer': f'News agent error: HTTP {resp.status_code}',
                    'data': None, 'chart': None, 'suggestions': None
                }

            data = resp.json()
            answer = data.get('answer', '')

            sources = data.get('sources_used', [])
            if sources:
                answer += '\n\n**Sources:**'
                for s in sources[:5]:
                    title = s.get('title', '')
                    link = s.get('link', '')
                    source_name = s.get('source', '')
                    date = s.get('date_iso', '')[:10]
                    if link:
                        answer += f'\n- [{title}]({link}) ({source_name}, {date})'
                    else:
                        answer += f'\n- {title} ({source_name}, {date})'

            suggestions = self._generate_suggestions(message, data)

            return {
                'answer': answer,
                'data': None,
                'chart': None,
                'suggestions': suggestions
            }

        except requests.Timeout:
            return {
                'answer': 'News agent request timed out. Please try again.',
                'data': None, 'chart': None, 'suggestions': None
            }
        except Exception as e:
            return {
                'answer': f'News agent error: {str(e)}',
                'data': None, 'chart': None, 'suggestions': None
            }

    def _generate_suggestions(self, message, response_data):
        suggestions = []
        sources = response_data.get('sources_used', [])

        companies = set()
        countries = set()
        for s in sources:
            companies.update(s.get('companies', []))
            countries.update(s.get('countries', []))

        if companies:
            company = list(companies)[0]
            suggestions.append(f'What else has {company} done recently?')
        if countries:
            country = list(countries)[0]
            suggestions.append(f'Any other regulatory changes in {country}?')
        if not suggestions:
            suggestions.append('What are the latest trends in the forex industry?')

        return suggestions[:3]
