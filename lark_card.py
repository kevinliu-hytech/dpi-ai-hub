"""
Lark Interactive Message Card builder.
Formats chatbot responses as rich cards for Lark.
"""


def build_response_card(answer, chart_image_key=None, chart_url=None, suggestions=None, **kwargs):
    """Build a Lark interactive card with answer, optional chart, and suggestions."""
    elements = []

    # Main answer text (markdown)
    elements.append({
        'tag': 'div',
        'text': {
            'tag': 'lark_md',
            'content': answer
        }
    })

    # Chart image
    if chart_image_key:
        elements.append({'tag': 'hr'})
        elements.append({
            'tag': 'img',
            'img_key': chart_image_key,
            'alt': {'tag': 'plain_text', 'content': '数据图表'},
            'mode': 'fit_horizontal'
        })

    # Suggestion buttons (clickable to trigger next query in-chat)
    if suggestions:
        elements.append({'tag': 'hr'})
        elements.append({
            'tag': 'div',
            'text': {'tag': 'lark_md', 'content': '**你可能还想问：**'}
        })
        actions = []
        for s in suggestions[:3]:
            actions.append({
                'tag': 'button',
                'text': {'tag': 'plain_text', 'content': s},
                'type': 'default',
                'value': {'action': 'digest_followup', 'question': s, 'type': 'internal'}
            })
        elements.append({
            'tag': 'action',
            'actions': actions
        })

    # Bottom actions
    elements.append({'tag': 'hr'})
    elements.append({
        'tag': 'action',
        'actions': [{
            'tag': 'button',
            'text': {'tag': 'plain_text', 'content': '🔄 开启新对话'},
            'type': 'default',
            'value': {'action': 'new_conversation'}
        }]
    })

    card = {
        'config': {'wide_screen_mode': True},
        'header': {
            'title': {'tag': 'plain_text', 'content': 'DPI AI 小助手'},
            'template': 'blue'
        },
        'elements': elements
    }

    return card


def build_error_card(error_msg):
    """Build a simple error/info card."""
    return {
        'config': {'wide_screen_mode': True},
        'header': {
            'title': {'tag': 'plain_text', 'content': 'DPI AI 小助手'},
            'template': 'blue'
        },
        'elements': [{
            'tag': 'div',
            'text': {'tag': 'lark_md', 'content': error_msg}
        }]
    }


def build_thinking_card():
    """Build a 'thinking...' card that will be updated with the real response."""
    return {
        'config': {'wide_screen_mode': True},
        'header': {
            'title': {'tag': 'plain_text', 'content': 'DPI AI 小助手'},
            'template': 'blue'
        },
        'elements': [{
            'tag': 'div',
            'text': {'tag': 'lark_md', 'content': '正在查询数据并分析中，请稍候...'}
        }]
    }
