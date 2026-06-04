"""
Lark Bot — Persistent Connection (WebSocket) mode.
Run as a standalone process: python lark_ws.py
"""
import os
import json
import time
import threading
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import lark_oapi as lark
from lark_oapi.adapter.flask import *
from lark_oapi import ws

from chat_engine import ChatEngine, load_conversations, save_conversations
from lark_card import build_response_card, build_error_card, build_thinking_card

LARK_APP_ID = os.getenv('LARK_APP_ID', '')
LARK_APP_SECRET = os.getenv('LARK_APP_SECRET', '')

chat_engine_instance = ChatEngine()

# Dedup: message_id → timestamp
_processed_messages = {}


def on_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    """Handle incoming messages from Lark."""
    message = data.event.message
    sender = data.event.sender

    # Dedup by message_id
    msg_id = message.message_id
    now = time.time()
    if msg_id in _processed_messages:
        print(f'[Lark] Dedup: skipping {msg_id}')
        return
    _processed_messages[msg_id] = now
    # Cleanup old entries
    expired = [k for k, v in _processed_messages.items() if now - v > 300]
    for k in expired:
        del _processed_messages[k]

    msg_type = message.message_type
    open_id = sender.sender_id.open_id

    if msg_type != 'text':
        send_card(open_id, build_error_card('目前仅支持文字消息'))
        return

    content = json.loads(message.content)
    text = content.get('text', '').strip()

    if not text:
        return

    # Handle "/new" command to reset conversation
    if text.lower() in ('/new', '新对话', '重新开始'):
        _reset_conversation(open_id)
        send_card(open_id, build_error_card('已开启新对话，之前的上下文已清空。'))
        return

    # Process in a separate thread to avoid blocking SDK callback
    threading.Thread(target=_process_and_reply, args=(open_id, text, msg_id), daemon=True).start()


def on_card_action(data):
    """Handle card button clicks (suggestions, new conversation)."""
    from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse

    action = data.event.action
    open_id = data.event.operator.open_id

    value = action.value or {}
    action_type = value.get('action', '')

    if action_type == 'new_conversation':
        _reset_conversation(open_id)
        # Send a visible divider so user sees the conversation boundary
        divider_card = {
            'config': {'wide_screen_mode': True},
            'header': {
                'title': {'tag': 'plain_text', 'content': '── 新对话 ──'},
                'template': 'grey'
            },
            'elements': [{
                'tag': 'div',
                'text': {'tag': 'lark_md', 'content': '上方为历史对话，下方开始新对话。直接输入问题即可。'}
            }]
        }
        send_card(open_id, divider_card)
        return P2CardActionTriggerResponse({
            'toast': {'type': 'info', 'content': '已开启新对话'}
        })

    if action_type == 'free_chat':
        return P2CardActionTriggerResponse({
            'toast': {'type': 'info', 'content': '请直接在对话框输入问题即可'}
        })

    if action_type == 'suggestion':
        text = value.get('text', '')
        if text:
            threading.Thread(target=_process_and_reply, args=(open_id, text, None), daemon=True).start()
            return P2CardActionTriggerResponse({
                'toast': {'type': 'info', 'content': '正在分析...'}
            })

    if action_type == 'digest_feedback':
        rating = value.get('rating', '')
        _record_digest_feedback(open_id, rating)
        label = '👍 感谢反馈！' if rating == 'good' else '👎 收到，我们会改进'
        return P2CardActionTriggerResponse({
            'toast': {'type': 'success', 'content': label}
        })

    if action_type == 'digest_followup':
        question = value.get('question', '')
        q_type = value.get('type', 'internal')
        if question:
            threading.Thread(
                target=_process_digest_followup,
                args=(open_id, question, q_type),
                daemon=True
            ).start()
            return P2CardActionTriggerResponse({
                'toast': {'type': 'info', 'content': '正在分析...'}
            })


    return P2CardActionTriggerResponse({})


# Demo mode: hardcoded full answers for known questions
DEMO_ANSWERS = {
    'STAR品牌本季度NRFR表现如何？对比目标完成情况': """STAR本季度NRFR（预估）表现强劲，季度进度仅63.7%已完成B级目标90.7%，A级目标也有望达成。

- 当前进度：NRFR (est.) QTD $19.5M，对B级目标$21.5M完成90.7%，对A级目标$30.4M完成64.1%
- 节奏领先：完成度90.7% vs 季度进度63.7%，领先27个百分点
- 季末预测：按当前速度线性外推可达$30.6M，B级超额42%，A级达成100.6%""",

    '本月各品牌的NDM表现如何？': """本月各品牌NDM整体表现稳健，总计1,247人，STAR贡献最大。

- STAR：524人（占比42%），环比+8%，保持领先
- VTJ：287人（占比23%），环比+15%，增长最快
- PU：198人（占比16%），环比-3%，略有下降
- MM：156人（占比13%），环比+2%，基本持平
- 其他品牌：82人（占比6%）""",

    'XM和Exness在YouTube的粉丝数和增长趋势对比': """XM和Exness在YouTube的表现对比：

- XM：粉丝12.3万，本月增长+2.1%（+2,500人），内容以教育类为主
- Exness：粉丝8.7万，本月增长+3.5%（+3,000人），增速更快，短视频策略见效
- 发布频率：XM本月12条，Exness本月18条
- 互动率：XM平均3.2%，Exness平均4.1%

Exness虽然基数小，但增长势头和互动率均优于XM。""",

    'Binance最近推出了什么新产品？': """Binance近期主要产品动态：

- 2026年5月推出SpaceX Pre-IPO永续合约，面向零售交易者开放
- 上线"Megadrop"积分空投平台，结合Web3钱包任务
- 推出机构级大宗交易（Block Trade）功能升级
- 扩展Copy Trading支持合约跟单

SpaceX合约是亮点产品，反映Binance在Pre-IPO资产类别的布局。"""
}

# Demo mode: fixed suggestions for known questions
DEMO_SUGGESTIONS = {
    'STAR品牌本季度NRFR表现如何？对比目标完成情况': [
        '对比所有品牌本季度NRFR目标完成度排名',
        'STAR本季度NRFR按月拆解趋势',
        'STAR近30天NRFR每日趋势图'
    ],
    '本月各品牌的NDM表现如何？': [
        'MM的NDM低是新客还是老客导致的',
        'VTJ高NDM主要来自哪些地区',
        'PU过去30天net deposit按地区趋势'
    ],
    'XM和Exness在YouTube的粉丝数和增长趋势对比': [
        'Which broker has the fastest growing TikTok',
        'XM近期发了什么内容',
        'Exness在哪些平台粉丝最多'
    ],
    'Binance最近推出了什么新产品？': [
        '越南最近有什么监管政策变化？',
        'CMC Markets的SpaceX交易产品是什么？',
        '亚洲最近有哪些新的加密交易所牌照？'
    ]
}


def _process_digest_followup(open_id, question, q_type):
    """Handle 'continue asking' from digest — show question then full analysis."""
    send_text(open_id, f'📝 {question}')
    thinking_msg_id = send_card(open_id, build_thinking_card())

    try:
        import time
        # Use hardcoded demo answer if available, with delay to simulate query
        if question in DEMO_ANSWERS:
            time.sleep(4)
            answer = DEMO_ANSWERS[question]
            suggestions = DEMO_SUGGESTIONS.get(question, [])
            card = build_response_card(
                answer=answer,
                chart_image_key=None,
                chart_url=None,
                suggestions=suggestions
            )
        else:
            if q_type == 'external_social':
                from external_data_agent import ExternalDataAgent
                agent = ExternalDataAgent()
                response = agent.chat(question, history=[])
            elif q_type == 'external_news' or q_type == 'external':
                from external_news_agent import ExternalNewsAgent
                agent = ExternalNewsAgent()
                response = agent.chat(question, history=[])
            else:
                response = handle_internal_data(open_id, question)

            suggestions = DEMO_SUGGESTIONS.get(question, response.get('suggestions', []))
            card = build_response_card(
                answer=response.get('answer', ''),
                chart_image_key=response.get('chart_image_key'),
                chart_url=response.get('chart_url'),
                suggestions=suggestions
            )

        if thinking_msg_id:
            update_card(thinking_msg_id, card)
        else:
            send_card(open_id, card)

    except Exception as e:
        print(f'[Lark] Digest followup error: {e}')
        error_card = build_error_card(f'处理出错：{str(e)}')
        if thinking_msg_id:
            update_card(thinking_msg_id, error_card)
        else:
            send_card(open_id, error_card)




def _record_digest_feedback(open_id, rating):
    """Record digest feedback from card button click."""
    try:
        from user_memory import UserMemory
        import boto3
        session = boto3.Session(
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        bedrock = session.client('bedrock-runtime')
        memory = UserMemory(bedrock_client=bedrock)
        memory.record_feedback(open_id, 'daily_digest', rating)
        print(f'[Lark] Digest feedback: {open_id} → {rating}')
    except Exception as e:
        print(f'[Lark] Digest feedback error: {e}')


def _reset_conversation(open_id):
    """Clear conversation history for a user."""
    conversations = load_conversations()
    conv_key = f'lark_{open_id}'
    if conv_key in conversations:
        del conversations[conv_key]
        save_conversations(conversations)
    print(f'[Lark] Conversation reset for {open_id}')


def _process_and_reply(open_id, text, msg_id):
    """Process message and send reply (runs in background thread)."""
    # Send "thinking" card first
    thinking_msg_id = send_card(open_id, build_thinking_card())

    try:
        # Route to appropriate agent
        from hub_router import HubRouter
        router = HubRouter()
        route_result = router.route(text)
        agent = route_result.get('agent', 'internal_data')
        print(f'[Lark] Routed "{text[:30]}" → {agent}')

        if agent == 'external_social':
            from external_data_agent import ExternalDataAgent
            ext_agent = ExternalDataAgent()
            response = ext_agent.chat(text, history=[])
        elif agent == 'external_news':
            from external_news_agent import ExternalNewsAgent
            news_agent = ExternalNewsAgent()
            response = news_agent.chat(text, history=[])
        else:
            response = handle_internal_data(open_id, text)

        card = build_response_card(
            answer=response.get('answer', ''),
            chart_image_key=response.get('chart_image_key'),
            chart_url=response.get('chart_url'),
            suggestions=response.get('suggestions', [])
        )

        # Update the thinking card with actual response
        if thinking_msg_id:
            update_card(thinking_msg_id, card)
        else:
            send_card(open_id, card)

    except Exception as e:
        print(f'[Lark] Error processing message: {e}')
        error_card = build_error_card(f'处理出错：{str(e)}')
        if thinking_msg_id:
            update_card(thinking_msg_id, error_card)
        else:
            send_card(open_id, error_card)


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
        print(f'[Lark] Response keys: {list(response.keys())}, chart: {bool(charts)}, chart_type: {charts[0].get("type") if charts and isinstance(charts, list) and len(charts) > 0 else "N/A"}')
        if charts:
            chart_image_key = generate_chart_screenshot(charts, response.get('data'))
            print(f'[Lark] Chart image_key: {chart_image_key}')
            if chart_image_key:
                result['chart_image_key'] = chart_image_key
                result['chart_url'] = f"http://18.136.250.8/gbis-analysis/chat"

        return result

    except Exception as e:
        save_conversations(conversations)
        return {
            'answer': f'分析出错：{str(e)}',
            'suggestions': [],
            'chart_image_key': None,
            'chart_url': None
        }


def _generate_progress_chart(chart_config):
    """Generate a horizontal bar chart representing progress bars."""
    try:
        import plotly.graph_objects as go

        items = chart_config.get('items', [])
        if not items:
            return None

        labels = [item.get('label', '') for item in reversed(items)]
        currents = [item.get('current', 0) for item in reversed(items)]
        targets = [item.get('target', 1) for item in reversed(items)]
        percentages = [round(c / t * 100, 1) if t else 0 for c, t in zip(currents, targets)]

        fig = go.Figure()

        # Background (target = 100%)
        fig.add_trace(go.Bar(
            y=labels, x=[100] * len(labels),
            orientation='h', marker_color='#E8E8E8',
            showlegend=False, hoverinfo='skip'
        ))

        # Progress fill
        colors = ['#4CAF50' if p >= 100 else '#2196F3' if p >= 70 else '#FF9800' for p in percentages]
        fig.add_trace(go.Bar(
            y=labels, x=[min(p, 100) for p in percentages],
            orientation='h', marker_color=colors,
            text=[f'{p}%' for p in percentages],
            textposition='inside', textfont=dict(color='white', size=14),
            showlegend=False
        ))

        fig.update_layout(
            barmode='overlay',
            template='plotly_white',
            width=700, height=max(200, len(items) * 70 + 80),
            font=dict(family='Noto Sans CJK SC, Noto Sans, sans-serif', size=13),
            margin=dict(l=160, r=40, t=30, b=30),
            xaxis=dict(range=[0, 110], showticklabels=False, showgrid=False),
            yaxis=dict(showgrid=False)
        )

        img_bytes = fig.to_image(format='png', engine='kaleido')
        image_key = upload_image_to_lark(img_bytes)
        return image_key

    except Exception as e:
        print(f'[Lark] Progress chart failed: {e}')
        return None


def generate_chart_screenshot(charts, data):
    """Generate a chart PNG using Plotly/Kaleido and upload to Lark."""
    try:
        import plotly.graph_objects as go

        if not charts or not data:
            return None

        chart_config = charts[0] if isinstance(charts, list) else charts
        if chart_config.get('type') == 'progress':
            return _generate_progress_chart(chart_config)

        chart_type = chart_config.get('type', 'bar')
        x_key = chart_config.get('x')
        y_key = chart_config.get('y')
        color_key = chart_config.get('color')
        title = chart_config.get('title', '')

        if not x_key or not y_key:
            return None

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
            x_vals = [row.get(x_key) for row in data]
            y_vals = [row.get(y_key) for row in data]
            if chart_type == 'line':
                fig.add_trace(go.Scatter(x=x_vals, y=y_vals, mode='lines+markers'))
            else:
                fig.add_trace(go.Bar(x=x_vals, y=y_vals))

        fig.update_layout(title=title, template='plotly_white', width=800, height=400,
                          font=dict(family='Noto Sans CJK SC, Noto Sans, sans-serif'))

        img_bytes = fig.to_image(format='png', engine='kaleido')
        image_key = upload_image_to_lark(img_bytes)
        return image_key

    except Exception as e:
        print(f'[Lark] Chart screenshot failed: {e}')
        return None


def upload_image_to_lark(image_bytes):
    """Upload image to Lark and return image_key."""
    import requests as req

    token = get_tenant_token()
    url = 'https://open.larksuite.com/open-apis/im/v1/images'
    headers = {'Authorization': f'Bearer {token}'}
    resp = req.post(url, headers=headers, files={
        'image': ('chart.png', image_bytes, 'image/png')
    }, data={'image_type': 'message'})
    data = resp.json()
    if data.get('code') != 0:
        print(f'[Lark] Image upload failed: {data}')
    return data.get('data', {}).get('image_key', '')


_token_cache = {'token': '', 'expires': 0}


def get_tenant_token():
    """Get tenant access token."""
    import requests as req

    now = time.time()
    if _token_cache['token'] and _token_cache['expires'] > now:
        return _token_cache['token']

    resp = req.post('https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal', json={
        'app_id': LARK_APP_ID,
        'app_secret': LARK_APP_SECRET
    })
    data = resp.json()
    _token_cache['token'] = data.get('tenant_access_token', '')
    _token_cache['expires'] = now + data.get('expire', 7200) - 300
    return _token_cache['token']


def send_text(open_id, text):
    """Send a plain text message to user."""
    import requests as req

    token = get_tenant_token()
    url = 'https://open.larksuite.com/open-apis/im/v1/messages'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'receive_id': open_id,
        'msg_type': 'text',
        'content': json.dumps({'text': text})
    }
    resp = req.post(url, headers=headers, json=payload, params={'receive_id_type': 'open_id'})
    result = resp.json()
    if result.get('code') != 0:
        print(f'[Lark] Send text failed: {result}')


def send_card(open_id, card):
    """Send interactive card to user. Returns message_id for later updates."""
    import requests as req

    token = get_tenant_token()
    url = 'https://open.larksuite.com/open-apis/im/v1/messages'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'receive_id': open_id,
        'msg_type': 'interactive',
        'content': json.dumps(card)
    }
    resp = req.post(url, headers=headers, json=payload, params={'receive_id_type': 'open_id'})
    result = resp.json()
    if result.get('code') != 0:
        print(f'[Lark] Send card failed: {result}')
        return None
    return result.get('data', {}).get('message_id', '')


def update_card(message_id, card):
    """Update an existing card message."""
    import requests as req

    token = get_tenant_token()
    url = f'https://open.larksuite.com/open-apis/im/v1/messages/{message_id}'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'msg_type': 'interactive',
        'content': json.dumps(card)
    }
    resp = req.patch(url, headers=headers, json=payload)
    result = resp.json()
    if result.get('code') != 0:
        print(f'[Lark] Update card failed: {result}')


# --- Main: Start WebSocket client ---

def main():
    from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger

    event_handler = lark.EventDispatcherHandler.builder(
        LARK_APP_SECRET, ''
    ).register_p2_im_message_receive_v1(
        on_message
    ).register_p2_card_action_trigger(
        on_card_action
    ).build()

    cli = ws.Client(
        LARK_APP_ID,
        LARK_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
        domain=lark.LARK_DOMAIN
    )

    print(f'[Lark Bot] Starting WebSocket connection...')
    print(f'[Lark Bot] App ID: {LARK_APP_ID}')
    cli.start()


if __name__ == '__main__':
    main()
