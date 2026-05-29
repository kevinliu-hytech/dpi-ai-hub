"""
Lark Bot Integration Layer
Receives messages from Lark → routes to agents → returns card messages
"""
import os
import json
import time
import hashlib
import requests
from datetime import datetime

from lark_router import LarkRouter
from lark_card import build_response_card, build_error_card
from chat_engine import ChatEngine, load_conversations, save_conversations

LARK_APP_ID = os.getenv('LARK_APP_ID', '')
LARK_APP_SECRET = os.getenv('LARK_APP_SECRET', '')
LARK_VERIFICATION_TOKEN = os.getenv('LARK_VERIFICATION_TOKEN', '')
LARK_ENCRYPT_KEY = os.getenv('LARK_ENCRYPT_KEY', '')

LARK_API_BASE = 'https://open.larksuite.com/open-apis'

_tenant_token_cache = {'token': '', 'expires': 0}


def get_tenant_access_token():
    """Get Lark tenant access token (cached)."""
    now = time.time()
    if _tenant_token_cache['token'] and _tenant_token_cache['expires'] > now:
        return _tenant_token_cache['token']

    resp = requests.post(f'{LARK_API_BASE}/auth/v3/tenant_access_token/internal', json={
        'app_id': LARK_APP_ID,
        'app_secret': LARK_APP_SECRET
    })
    data = resp.json()
    token = data.get('tenant_access_token', '')
    _tenant_token_cache['token'] = token
    _tenant_token_cache['expires'] = now + data.get('expire', 7200) - 300
    return token


def send_lark_message(open_id, msg_type, content):
    """Send a message to a Lark user via open_id."""
    token = get_tenant_access_token()
    url = f'{LARK_API_BASE}/im/v1/messages'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'receive_id': open_id,
        'msg_type': msg_type,
        'content': content if isinstance(content, str) else json.dumps(content)
    }
    resp = requests.post(url, headers=headers, json=payload, params={'receive_id_type': 'open_id'})
    return resp.json()


def send_lark_card(open_id, card):
    """Send an interactive card message."""
    return send_lark_message(open_id, 'interactive', json.dumps(card))


def upload_image(image_bytes):
    """Upload an image to Lark and return image_key."""
    token = get_tenant_access_token()
    url = f'{LARK_API_BASE}/im/v1/images'
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.post(url, headers=headers, files={
        'image': ('chart.png', image_bytes, 'image/png')
    }, data={'image_type': 'message'})
    data = resp.json()
    return data.get('data', {}).get('image_key', '')


# --- Event Processing ---

_processed_events = {}  # event_id → timestamp, for dedup

chat_engine_instance = ChatEngine()


def handle_lark_event(event_body):
    """Main entry point for Lark webhook events."""
    # Challenge verification (first-time setup)
    if 'challenge' in event_body:
        return {'challenge': event_body['challenge']}

    # Schema v2 event
    header = event_body.get('header', {})
    event = event_body.get('event', {})

    event_id = header.get('event_id', '')
    if event_id in _processed_events:
        return {'ok': True}
    _processed_events[event_id] = time.time()
    _cleanup_old_events()

    event_type = header.get('event_type', '')
    if event_type != 'im.message.receive_v1':
        return {'ok': True}

    message = event.get('message', {})
    sender = event.get('sender', {})

    msg_type = message.get('message_type', '')
    if msg_type != 'text':
        open_id = sender.get('sender_id', {}).get('open_id', '')
        if open_id:
            send_lark_card(open_id, build_error_card('目前仅支持文字消息'))
        return {'ok': True}

    content = json.loads(message.get('content', '{}'))
    text = content.get('text', '').strip()
    open_id = sender.get('sender_id', {}).get('open_id', '')

    if not text or not open_id:
        return {'ok': True}

    process_user_message(open_id, text)
    return {'ok': True}


def process_user_message(open_id, text):
    """Route user message to appropriate agent and respond."""
    router = LarkRouter()
    route_result = router.route(text)
    agent_name = route_result.get('agent', 'internal_data')

    if agent_name == 'internal_data':
        response = handle_internal_data(open_id, text)
    else:
        response = {
            'answer': f'Agent "{agent_name}" 暂未接入，敬请期待。',
            'chart': None,
            'suggestions': []
        }

    card = build_response_card(
        answer=response.get('answer', ''),
        chart_image_key=response.get('chart_image_key'),
        chart_url=response.get('chart_url'),
        suggestions=response.get('suggestions', [])
    )
    send_lark_card(open_id, card)


def handle_internal_data(open_id, text):
    """Handle internal data analysis using existing ChatEngine."""
    conversations = load_conversations()
    conv_key = f'lark_{open_id}'

    if conv_key not in conversations:
        conversations[conv_key] = []

    conversations[conv_key].append({
        'role': 'user',
        'content': text,
        'timestamp': datetime.now().isoformat()
    })

    history = conversations[conv_key]

    try:
        response = chat_engine_instance.chat(text, history[:-1])

        conversations[conv_key].append({
            'role': 'assistant',
            'content': response['answer'],
            'timestamp': datetime.now().isoformat()
        })
        save_conversations(conversations)

        result = {
            'answer': response['answer'],
            'suggestions': response.get('suggestions', []),
            'chart_image_key': None,
            'chart_url': None
        }

        # Generate chart screenshot if chart config exists
        charts = response.get('chart')
        if charts:
            chart_image_key = generate_chart_screenshot(charts, response.get('data'))
            if chart_image_key:
                result['chart_image_key'] = chart_image_key
                result['chart_url'] = f"http://18.136.250.8:5000/chat/view/{conv_key}"

        return result

    except Exception as e:
        save_conversations(conversations)
        return {
            'answer': f'分析出错：{str(e)}',
            'suggestions': [],
            'chart_image_key': None,
            'chart_url': None
        }


def generate_chart_screenshot(charts, data):
    """Generate a chart PNG using Plotly/Kaleido and upload to Lark."""
    try:
        import plotly.graph_objects as go

        if not charts or not data:
            return None

        chart_config = charts[0] if isinstance(charts, list) else charts
        if chart_config.get('type') == 'progress':
            return None

        chart_type = chart_config.get('type', 'bar')
        x_key = chart_config.get('x')
        y_key = chart_config.get('y')
        color_key = chart_config.get('color')
        title = chart_config.get('title', '')

        if not x_key or not y_key:
            return None

        x_vals = [row.get(x_key) for row in data]
        y_vals = [row.get(y_key) for row in data]

        fig = go.Figure()

        if color_key:
            groups = {}
            for row in data:
                g = str(row.get(color_key, ''))
                if g not in groups:
                    groups[g] = {'x': [], 'y': []}
                groups[g]['x'].append(row.get(x_key))
                groups[g]['y'].append(row.get(y_key))

            for g_name, g_data in groups.items():
                if chart_type == 'line':
                    fig.add_trace(go.Scatter(x=g_data['x'], y=g_data['y'], mode='lines+markers', name=g_name))
                else:
                    fig.add_trace(go.Bar(x=g_data['x'], y=g_data['y'], name=g_name))
        else:
            if chart_type == 'line':
                fig.add_trace(go.Scatter(x=x_vals, y=y_vals, mode='lines+markers'))
            else:
                fig.add_trace(go.Bar(x=x_vals, y=y_vals))

        fig.update_layout(title=title, template='plotly_white', width=800, height=400,
                          font=dict(family='Noto Sans CJK SC, Noto Sans, sans-serif'))

        img_bytes = fig.to_image(format='png', engine='kaleido')
        image_key = upload_image(img_bytes)
        return image_key

    except Exception as e:
        print(f'[Lark] Chart screenshot failed: {e}')
        return None


def _cleanup_old_events():
    """Remove event IDs older than 5 minutes."""
    now = time.time()
    expired = [k for k, v in _processed_events.items() if now - v > 300]
    for k in expired:
        del _processed_events[k]
