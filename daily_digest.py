"""
Daily Digest — Generates personalized daily briefings and pushes via Lark.
Scheduled to run once per day (via cron or manual trigger).
Flow: Load user profiles → Generate questions → Query data → Build Lark card → Push
"""
import os
import json
import boto3
import re
from datetime import datetime

from user_memory import UserMemory
from chat_engine import ChatEngine
from lark_bot import send_lark_card, get_tenant_access_token

# AI Hub URL (opened in Lark webview)
HUB_BASE_URL = os.getenv('HUB_BASE_URL', 'http://18.136.250.8/gbis-ai-hub/hub')
DIGEST_TOKEN = os.getenv('DIGEST_AUTO_TOKEN', 'yDTsLSsMoW54xZRrWY1bks7EjMhjNiea')

# Users to push to: email → lark open_id
# TODO: Replace with Lark API lookup once contact:user.id:readonly permission granted
DIGEST_USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'digest_users.json')

DEFAULT_TOPICS = ['NRFR', 'trading volume', 'FTD', 'brand performance', 'NDM']


def load_digest_users():
    if os.path.exists(DIGEST_USERS_FILE):
        with open(DIGEST_USERS_FILE, 'r') as f:
            return json.load(f)
    return {}


def _init_bedrock():
    session = boto3.Session(
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
    )
    return session.client('bedrock-runtime')


def _call_haiku(bedrock, prompt, max_tokens=500):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    response = bedrock.invoke_model(
        modelId='us.anthropic.claude-3-5-haiku-20241022-v1:0',
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body)
    )
    result = json.loads(response['body'].read())
    return result['content'][0]['text']


def generate_digest_questions(bedrock, topics, user_name=''):
    today = datetime.now().strftime('%Y-%m-%d')
    topics_str = ', '.join(topics) if topics else ', '.join(DEFAULT_TOPICS)

    prompt = f"""Today is {today}. Generate exactly 4 data questions in Chinese for an executive daily briefing.

The user cares about: {topics_str}

Requirements:
- 2 questions about INTERNAL data (brand KPIs: NRFR, FTD, trading volume, revenue, TDAU, NDM)
- 2 questions about EXTERNAL data (competitor social media: followers, content, engagement)
- Questions should be about TODAY's or THIS WEEK's latest data
- Keep each question under 25 characters
- Tag each as "internal" or "external"

Output JSON array only:
[{{"q": "question", "type": "internal"}}, {{"q": "question", "type": "external"}}, ...]"""

    try:
        result = _call_haiku(bedrock, prompt, max_tokens=300)
        match = re.search(r'\[.*\]', result, re.DOTALL)
        if match:
            questions = json.loads(match.group())
            return questions[:4]
    except Exception as e:
        print(f'[Digest] Question generation failed: {e}')

    return [
        {'q': '今日各品牌FTD表现如何？', 'type': 'internal'},
        {'q': '本周交易量趋势如何？', 'type': 'internal'},
        {'q': 'XM近期社媒粉丝变化？', 'type': 'external'},
        {'q': '竞品本周发布了什么内容？', 'type': 'external'}
    ]


def get_brief_answers(chat_engine, external_agent, bedrock, questions):
    """Get one-sentence summary for each question."""
    results = []
    for item in questions:
        q = item['q'] if isinstance(item, dict) else item
        q_type = item.get('type', 'internal') if isinstance(item, dict) else 'internal'

        try:
            if q_type == 'external_social':
                response = external_agent.chat(q, history=[])
            elif q_type == 'external_news':
                from external_news_agent import ExternalNewsAgent
                news_agent = ExternalNewsAgent()
                response = news_agent.chat(q, history=[])
            elif q_type == 'external':
                response = external_agent.chat(q, history=[])
            else:
                response = chat_engine.chat(q, history=[])

            answer = response.get('answer', '')
            summary = _summarize_to_one_line(bedrock, q, answer)
            results.append({'question': q, 'summary': summary, 'type': q_type})
        except Exception as e:
            print(f'[Digest] Error for "{q}": {e}')
            results.append({'question': q, 'summary': '点击查看详情', 'type': q_type})
    return results


def _summarize_to_one_line(bedrock, question, answer):
    """Compress an answer to a single sentence with key data point."""
    if len(answer) <= 50:
        return answer

    prompt = f"""将以下回答压缩为1句话（不超过40个字），保留最关键的数字或结论：

问题：{question}
回答：{answer[:500]}

只输出压缩后的一句话："""

    try:
        result = _call_haiku(bedrock, prompt, max_tokens=80)
        return result.strip().strip('"').strip()
    except:
        # Fallback: first sentence
        first_line = answer.split('\n')[0][:50]
        return first_line


def _lark_webview_url(url):
    """Wrap URL so it opens inside Lark's built-in browser, with auto-login token."""
    sep = '&' if '?' in url else '?'
    url_with_token = f"{url}{sep}token={DIGEST_TOKEN}"
    return f"https://applink.larksuite.com/client/web_url/open?url={requests_quote(url_with_token)}"


def build_digest_card(user_name, digest_items, date_str):
    """Build a Lark card for daily digest — compact format."""
    elements = []

    internal_items = [i for i in digest_items if i.get('type') == 'internal']
    external_items = [i for i in digest_items if i.get('type') in ('external', 'external_social', 'external_news')]

    # Internal section
    num = 1
    if internal_items:
        elements.append({
            'tag': 'div',
            'text': {'tag': 'lark_md', 'content': '**📈 内部表现**'}
        })
        for item in internal_items:
            elements.append({
                'tag': 'div',
                'text': {'tag': 'lark_md', 'content': f"**{num}. {item['question']}**\n{item['summary']}"}
            })
            elements.append({
                'tag': 'action',
                'actions': [{
                    'tag': 'button',
                    'text': {'tag': 'plain_text', 'content': '继续追问 →'},
                    'type': 'default',
                    'value': {'action': 'digest_followup', 'question': item['question'], 'type': item['type']}
                }]
            })
            num += 1

    # External section
    if external_items:
        elements.append({'tag': 'hr'})
        elements.append({
            'tag': 'div',
            'text': {'tag': 'lark_md', 'content': '**🌐 外部趋势**'}
        })
        for item in external_items:
            elements.append({
                'tag': 'div',
                'text': {'tag': 'lark_md', 'content': f"**{num}. {item['question']}**\n{item['summary']}"}
            })
            elements.append({
                'tag': 'action',
                'actions': [{
                    'tag': 'button',
                    'text': {'tag': 'plain_text', 'content': '继续追问 →'},
                    'type': 'default',
                    'value': {'action': 'digest_followup', 'question': item['question'], 'type': item['type']}
                }]
            })
            num += 1

    # Footer: free chat + feedback
    elements.append({'tag': 'hr'})
    elements.append({
        'tag': 'action',
        'actions': [
            {
                'tag': 'button',
                'text': {'tag': 'plain_text', 'content': '💬 自由提问'},
                'type': 'primary',
                'value': {'action': 'free_chat'}
            },
            {
                'tag': 'button',
                'text': {'tag': 'plain_text', 'content': '👍 有用'},
                'type': 'default',
                'value': {'action': 'digest_feedback', 'rating': 'good'}
            },
            {
                'tag': 'button',
                'text': {'tag': 'plain_text', 'content': '👎 没用'},
                'type': 'default',
                'value': {'action': 'digest_feedback', 'rating': 'bad'}
            }
        ]
    })

    card = {
        'config': {'wide_screen_mode': True},
        'header': {
            'title': {'tag': 'plain_text', 'content': f'DPI AI 每日简报 - {date_str}'},
            'template': 'blue'
        },
        'elements': elements
    }

    return card


def requests_quote(text):
    """URL-encode a string."""
    from urllib.parse import quote
    return quote(text, safe='')


DEMO_QUESTIONS = [
    {'q': 'STAR品牌本季度NRFR表现如何？对比目标完成情况', 'type': 'internal'},
    {'q': '本月各品牌的NDM表现如何？', 'type': 'internal'},
    {'q': 'XM和Exness在YouTube的粉丝数和增长趋势对比', 'type': 'external_social'},
    {'q': 'Binance最近推出了什么新产品？', 'type': 'external_news'}
]

DEMO_SUMMARIES = [
    {'question': 'STAR品牌本季度NRFR表现如何？对比目标完成情况', 'summary': 'STAR本季NRFR $19.5M，B级目标完成90.7%，A级64.1%，按当前节奏季末可超额完成', 'type': 'internal'},
    {'question': '本月各品牌的NDM表现如何？', 'summary': '本月NDM总计1,247人，STAR贡献42%领先，VTJ环比增长15%表现突出', 'type': 'internal'},
    {'question': 'XM和Exness在YouTube的粉丝数和增长趋势对比', 'summary': 'XM YouTube粉丝12.3万，Exness 8.7万；XM本月增长2.1%，Exness增长3.5%', 'type': 'external_social'},
    {'question': 'Binance最近推出了什么新产品？', 'summary': 'Binance于5月推出SpaceX Pre-IPO永续合约，面向零售交易者', 'type': 'external_news'}
]


def run_digest(demo=False):
    """Main entry: generate and push daily digest to all configured users."""
    print(f'[Digest] Starting daily digest at {datetime.now().isoformat()}')

    digest_users = load_digest_users()
    if not digest_users:
        print('[Digest] No users configured in digest_users.json')
        return

    today_str = datetime.now().strftime('%m月%d日')

    if not demo:
        bedrock = _init_bedrock()
        user_memory = UserMemory(bedrock_client=bedrock)
        chat_engine = ChatEngine()
        from external_data_agent import ExternalDataAgent
        external_agent = ExternalDataAgent()

    for email, config in digest_users.items():
        open_id = config.get('open_id')
        name = config.get('name', email.split('@')[0])

        if not open_id:
            print(f'[Digest] Skipping {email}: no open_id')
            continue

        print(f'[Digest] Generating for {name} ({email})...')

        if demo:
            digest_items = DEMO_SUMMARIES
        else:
            topics = user_memory.get_topics(email) or DEFAULT_TOPICS
            questions = generate_digest_questions(bedrock, topics, name)
            digest_items = get_brief_answers(chat_engine, external_agent, bedrock, questions)

        # Build and send card
        card = build_digest_card(name, digest_items, today_str)
        result = send_lark_card(open_id, card)
        print(f'[Digest] Sent to {name}: {result.get("msg", "unknown")}')

    print(f'[Digest] Done.')


if __name__ == '__main__':
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    demo_mode = '--demo' in sys.argv
    run_digest(demo=demo_mode)
