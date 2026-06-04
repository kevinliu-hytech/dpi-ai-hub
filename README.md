# Pulse Insight

Unified analytics chatbot with intelligent 3-way routing. Questions are classified by intent and dispatched to the appropriate data engine.

## Architecture

```
User Question (Web / Lark Bot)
     │
     ▼
┌─────────────┐
│  Hub Router  │  (Haiku — intent classification)
└─────┬───────┘
      │
  ┌───┼────────────┐
  ▼   ▼            ▼
Internal   External     External
  Data     Social       News
  Agent    Agent        Agent
  │          │            │
  ▼          ▼            ▼
Databricks  Competitor   BI Digest
  SQL       REST API     Chatbot API
  │          │            │
  ▼          ▼            ▼
┌──────────────────────────────┐
│      Response Layer          │
│  (Chart + Suggestions + MD)  │
└──────────────────────────────┘
```

### Agents

| Agent | Scope | Data Source |
|-------|-------|-------------|
| **Internal Data** | Brand KPIs (NRFR, TDAU, FTD, NDM, trading volume, revenue) for GS/STAR/VTJ/PU/APAC/MM/UM/VT | Databricks SQL |
| **External Social** | Competitor social media metrics (YouTube, TikTok, Facebook, Instagram, X) | [Competitor Dashboard API](https://github.com/chiachunghytech/Competitor-Dashboard-Study) |
| **External News** | Industry news, regulatory changes, competitor product launches | [BI Digest Chatbot API](https://github.com/maiphanhytech/bi-digest-chatbot) |

### External Dependencies

This repo is the **main orchestration layer**. It calls two external agent APIs deployed on the same EC2 instance:

| Service | Repo | Endpoint | Auth |
|---------|------|----------|------|
| Competitor Social Media | [chiachunghytech/Competitor-Dashboard-Study](https://github.com/chiachunghytech/Competitor-Dashboard-Study) | `http://localhost:8764/competitor-api` | API Key |
| BI Digest Chatbot | [maiphanhytech/bi-digest-chatbot](https://github.com/maiphanhytech/bi-digest-chatbot) | `http://localhost:5022/bi-digest-chatbot/ask` | None (internal) |

## Tech Stack

- **Backend**: Flask + Gunicorn
- **LLM**: Claude via AWS Bedrock (Opus for analysis, Haiku for routing/planning)
- **Database**: Databricks SQL (internal business data)
- **Frontend**: Vanilla JS + Plotly.js
- **Bot**: Lark WebSocket (real-time messaging + card callbacks)
- **Deployment**: EC2 behind Nginx reverse proxy
- **Daily Digest**: Automated daily briefing via Lark push

## Features

- **3-Way Intelligent Routing** — Haiku classifies questions into internal data / competitor social / industry news
- **Multi-turn Conversation** — Context-aware follow-up questions within same agent
- **Auto Visualization** — Charts generated based on data shape (line/bar/progress)
- **Daily Digest** — Personalized daily briefing with key metrics, pushed via Lark
- **Lark Card Callbacks** — Interactive buttons (follow-up, feedback) without leaving chat
- **Multi-language** — Chinese/English detection with appropriate response language
- **Eval Framework** — Test cases for routing accuracy, SQL correctness, chart decisions

## Project Structure

```
├── app.py                      # Flask routes — main entry point
├── hub_router.py               # 3-way intent classifier (Haiku)
├── chat_engine.py              # Internal data agent (SQL gen + analysis)
├── external_data_agent.py      # External social media agent (competitor API)
├── external_news_agent.py      # External news agent (BI digest chatbot API)
├── daily_digest.py             # Daily briefing generator + Lark push
├── lark_ws.py                  # Lark WebSocket client + card callback handlers
├── lark_card.py                # Lark interactive card builder
├── lark_bot.py                 # Lark webhook handler (legacy)
├── hub_logger.py               # Request logging (structured JSON)
├── user_memory.py              # User preference tracking
├── config.py                   # App configuration
├── query_loader.py             # Few-shot SQL example loader
├── ai_query_generator_bedrock.py  # SQL generation via Bedrock
├── prompts/                    # LLM prompt templates
│   ├── router.md               # 3-way routing prompt
│   ├── internal_chart_decision.md
│   ├── external_planner.md
│   ├── external_analyst_en.md
│   └── external_analyst_zh.md
├── kb/                         # Knowledge base for SQL generation
├── eval/                       # Evaluation test cases + runner
├── queries/                    # Few-shot SQL examples
├── templates/                  # Jinja2 HTML (hub, chat, admin pages)
├── static/                     # Frontend JS + CSS
├── docs/                       # Deployment & development guides
├── digest_users.json           # Lark push recipients config
├── requirements.txt            # Python dependencies
└── .env.example                # Required environment variables template
```

## Quick Start

```bash
# 1. Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in credentials

# 2. Run web app
python app.py          # http://localhost:5000

# 3. Run Lark bot (separate process)
python lark_ws.py

# 4. Trigger daily digest manually
python daily_digest.py
```

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Purpose |
|----------|---------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | AWS Bedrock access |
| `DATABRICKS_HOST` / `DATABRICKS_TOKEN` | Databricks SQL connection |
| `COMPETITOR_API_KEY` | Auth for competitor social media API |
| `LARK_APP_ID` / `LARK_APP_SECRET` | Lark bot credentials |

## Deployment

See [docs/deployment.md](docs/deployment.md) for EC2 deployment steps.

## Evaluation

```bash
python eval/run_eval.py
```

Tests routing accuracy, SQL generation, chart decisions, and language detection. See `eval/eval_cases.json`.

## Team

Developed by **Kevin Liu**, **Uyen Mai Phan Ngoc**, and **Lim Chia Chung** — DPI Department.
