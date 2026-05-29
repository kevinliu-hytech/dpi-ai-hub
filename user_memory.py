"""
User Memory — Tracks per-user interests and preferences.
Stores question history + feedback, periodically summarizes into a profile.
Used for: personalized daily digests, response tuning.
"""
import os
import json
import time
from datetime import datetime

PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_profiles')
os.makedirs(PROFILES_DIR, exist_ok=True)

SUMMARIZE_THRESHOLD = 10


class UserMemory:
    def __init__(self, bedrock_client=None, model_id='us.anthropic.claude-3-5-haiku-20241022-v1:0'):
        self.bedrock = bedrock_client
        self.model_id = model_id

    def _profile_path(self, email):
        safe_name = email.replace('@', '_at_').replace('.', '_')
        return os.path.join(PROFILES_DIR, f'{safe_name}.json')

    def _load_profile(self, email):
        path = self._profile_path(email)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'email': email,
            'questions': [],
            'feedback': [],
            'summary': None,
            'topics': [],
            'last_updated': None
        }

    def _save_profile(self, email, profile):
        profile['last_updated'] = datetime.utcnow().isoformat() + 'Z'
        path = self._profile_path(email)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

    def record_question(self, email, question, route=None):
        if not email:
            return
        profile = self._load_profile(email)
        profile['questions'].append({
            'q': question,
            'route': route,
            'ts': datetime.utcnow().isoformat() + 'Z'
        })
        # Keep last 100 questions
        profile['questions'] = profile['questions'][-100:]
        self._save_profile(email, profile)

        # Auto-summarize if enough new data since last summary
        unsummarized = self._count_since_last_summary(profile)
        if unsummarized >= SUMMARIZE_THRESHOLD and self.bedrock:
            self._update_summary(email, profile)

    def record_feedback(self, email, question, rating):
        if not email:
            return
        profile = self._load_profile(email)
        profile['feedback'].append({
            'q': question,
            'rating': rating,
            'ts': datetime.utcnow().isoformat() + 'Z'
        })
        # Keep last 50 feedback entries
        profile['feedback'] = profile['feedback'][-50:]
        self._save_profile(email, profile)

    def get_profile(self, email):
        if not email:
            return None
        profile = self._load_profile(email)
        return profile

    def get_summary(self, email):
        if not email:
            return None
        profile = self._load_profile(email)
        return profile.get('summary')

    def get_topics(self, email):
        if not email:
            return []
        profile = self._load_profile(email)
        return profile.get('topics', [])

    def _count_since_last_summary(self, profile):
        if not profile.get('summary'):
            return len(profile['questions'])
        last_summary_time = profile.get('_last_summary_ts', '')
        count = 0
        for q in reversed(profile['questions']):
            if q['ts'] > last_summary_time:
                count += 1
            else:
                break
        return count

    def _update_summary(self, email, profile):
        questions_text = '\n'.join(
            f"- {q['q']}" for q in profile['questions'][-30:]
        )
        feedback_text = '\n'.join(
            f"- [{fb['rating']}] {fb['q']}" for fb in profile['feedback'][-20:]
        )

        prompt = f"""Based on this user's recent questions and feedback, summarize their interests and preferences in 2-3 sentences. Also extract 3-8 topic keywords.

Recent questions:
{questions_text}

Feedback (good = liked, bad = disliked):
{feedback_text}

Output JSON:
{{"summary": "...", "topics": ["topic1", "topic2", ...]}}"""

        try:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            }
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body)
            )
            result = json.loads(response['body'].read())
            text = result['content'][0]['text']

            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                profile['summary'] = parsed.get('summary', '')
                profile['topics'] = parsed.get('topics', [])
                profile['_last_summary_ts'] = datetime.utcnow().isoformat() + 'Z'
                self._save_profile(email, profile)
        except Exception as e:
            print(f'[UserMemory] Summary update failed: {e}')
