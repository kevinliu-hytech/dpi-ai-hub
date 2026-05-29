import os
import json
import re
import boto3
from databricks import sql as databricks_sql


CONVERSATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chat_history.json')


class ChatEngine:
    def __init__(self):
        self.model_id = 'us.anthropic.claude-opus-4-7'
        self.bedrock = self._init_bedrock()
        self.knowledge_base = self._load_knowledge_base()
        self.chart_prompt = self._load_prompt('internal_chart_decision.md')

    def _init_bedrock(self):
        session = boto3.Session(
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
        return session.client('bedrock-runtime')

    def _load_knowledge_base(self):
        kb_path = os.path.join(os.path.dirname(__file__), 'kb', 'gbis_knowledge_base.md')
        if os.path.exists(kb_path):
            with open(kb_path, 'r') as f:
                return f.read()
        return ""

    def _load_prompt(self, filename):
        path = os.path.join(os.path.dirname(__file__), 'prompts', filename)
        if os.path.exists(path):
            with open(path, 'r') as f:
                return f.read()
        return ""

    def _get_db_connection(self):
        return databricks_sql.connect(
            server_hostname=os.getenv('DATABRICKS_SERVER_HOSTNAME'),
            http_path=os.getenv('DATABRICKS_HTTP_PATH'),
            access_token=os.getenv('DATABRICKS_ACCESS_TOKEN')
        )

    def _extract_mentioned_brands(self, text):
        all_brands = {'APAC', 'GS', 'VTJ', 'PU', 'STAR', 'MM', 'UM', 'VT'}
        found = set()
        for b in all_brands:
            pattern = r'(?<![a-zA-Z])' + re.escape(b) + r'(?![a-zA-Z])'
            if re.search(pattern, text, re.IGNORECASE):
                found.add(b)
        return found

    def _check_brand_coverage(self, mentioned_brands, data):
        if not mentioned_brands or not data or len(mentioned_brands) <= 1:
            return set()
        data_brands = set()
        for row in data:
            for val in row.values():
                if isinstance(val, str) and val.upper() in mentioned_brands:
                    data_brands.add(val.upper())
        missing = mentioned_brands - data_brands
        return missing

    def _check_sql_permission(self, sql):
        blocked_keywords = ['email', 'phone', 'address']
        sql_lower = sql.lower()
        for kw in blocked_keywords:
            if kw in sql_lower:
                return False, kw
        # user_id/account_id/client_id: allow in JOIN/WHERE/GROUP but block in SELECT output
        id_keywords = ['user_id', 'account_id', 'client_id']
        select_clause = sql_lower.split('from')[0] if 'from' in sql_lower else sql_lower
        for kw in id_keywords:
            if kw in select_clause:
                # Check if it's inside COUNT/SUM/etc (aggregated) — that's OK
                import re
                pattern = r'(count|sum|avg|min|max)\s*\(\s*(distinct\s+)?' + kw
                if not re.search(pattern, select_clause):
                    return False, kw
        return True, None

    def _execute_sql(self, sql):
        allowed, blocked_field = self._check_sql_permission(sql)
        if not allowed:
            return {'success': False, 'error': f'权限不足：不允许查询用户明细字段（{blocked_field}）'}
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute(sql)
            if cursor.description is None:
                cursor.close()
                conn.close()
                return {'success': True, 'data': [], 'columns': []}
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchmany(10000)
            from datetime import datetime, date as date_type
            def _clean_val(v):
                if isinstance(v, datetime):
                    return v.strftime('%Y-%m-%d')
                if isinstance(v, date_type):
                    return v.isoformat()
                return v
            data = [{col: _clean_val(val) for col, val in zip(columns, row)} for row in rows]
            cursor.close()
            conn.close()
            return {'success': True, 'data': data, 'columns': columns}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _build_context(self, history, system_prompt):
        recent_limit = 20
        if len(history) <= recent_limit:
            return [{'role': m['role'], 'content': m['content']} for m in history]

        old_msgs = history[:-recent_limit]
        recent_msgs = history[-recent_limit:]

        summary = self._summarize_history(old_msgs, system_prompt)
        messages = [{'role': 'user', 'content': f'[之前的对话摘要]\n{summary}'},
                    {'role': 'assistant', 'content': '好的，我已了解之前的对话内容，会延续相同的分析上下文。'}]
        for m in recent_msgs:
            messages.append({'role': m['role'], 'content': m['content']})
        return messages

    def _summarize_history(self, old_msgs, system_prompt):
        conversation_text = ''
        for m in old_msgs[-30:]:
            role_label = '用户' if m['role'] == 'user' else '助手'
            conversation_text += f'{role_label}: {m["content"][:300]}\n'

        summary_prompt = "请用3-5句话总结以下对话的核心话题、讨论的指标、得出的结论。保留关键数字和品牌名称。"
        msgs = [{'role': 'user', 'content': f'{summary_prompt}\n\n{conversation_text}'}]
        return self._call_llm(system_prompt, msgs, max_tokens=500)

    def _call_llm(self, system_prompt, messages, max_tokens=4000):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages
        }
        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body)
        )
        result = json.loads(response['body'].read())
        return result['content'][0]['text']

    def _call_haiku(self, prompt, max_tokens=500):
        """Fast Haiku call for validation/checking tasks."""
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{'role': 'user', 'content': prompt}]
        }
        response = self.bedrock.invoke_model(
            modelId='us.anthropic.claude-3-5-haiku-20241022-v1:0',
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body)
        )
        result = json.loads(response['body'].read())
        return result['content'][0]['text']

    def _decide_chart(self, data, question, is_en=False):
        if not data or len(data) <= 1:
            return None

        columns = list(data[0].keys())

        # Classify columns
        date_cols = []
        numeric_cols = []
        category_cols = []
        for c in columns:
            val = data[0].get(c)
            if isinstance(val, (int, float)):
                numeric_cols.append(c)
            elif re.match(r'\d{4}-\d{2}', str(val or '')):
                date_cols.append(c)
            else:
                category_cols.append(c)

        # Multi-metric time series: date + category + multiple numerics → one chart per metric
        if date_cols and category_cols and len(numeric_cols) >= 2:
            date_col = date_cols[0]
            n_dates = len(set(str(row.get(date_col, '')) for row in data))
            if n_dates >= 3:
                color_col = None
                for cc in category_cols:
                    uc = len(set(str(row.get(cc, '')) for row in data))
                    if 2 <= uc <= 10:
                        color_col = cc
                        break
                date_range = self._extract_date_range(data, columns)
                charts = []
                for y_col in numeric_cols:
                    label = self._COL_LABELS.get(y_col, y_col)
                    title = f'{label}趋势' if not is_en else f'{label} Trend'
                    if date_range:
                        title = f"{title} ({date_range})"
                    config = {'type': 'line', 'title': title, 'x': date_col, 'y': y_col}
                    if color_col:
                        config['color'] = color_col
                    charts.append(config)
                return charts

        # Single metric: use Haiku for decision
        sample = data[:5]
        data_summary = f"Columns: {columns}\nSample rows ({len(data)} total):\n{json.dumps(sample, default=str, ensure_ascii=False)[:800]}"

        prompt = f"""{self.chart_prompt}

Available columns: {columns}

Question: {question}

Data:
{data_summary}"""

        try:
            result = self._call_haiku(prompt, max_tokens=200)
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                decision = json.loads(match.group())
                if not decision.get('show'):
                    return None
                chart_type = decision.get('type', 'bar')
                x_col = decision.get('x')
                y_col = decision.get('y')
                color_col = decision.get('color')
                title = decision.get('title', '')
                if x_col and y_col and x_col in columns and y_col in columns:
                    date_range = self._extract_date_range(data, columns)
                    if date_range:
                        title = f"{title} ({date_range})"
                    config = {'type': chart_type, 'title': title, 'x': x_col, 'y': y_col}
                    if color_col and color_col in columns:
                        config['color'] = color_col
                    return [config]
        except Exception as e:
            print(f'[ChatEngine] Chart decision error: {e}')
        return None

    def _extract_date_range(self, data, columns):
        date_col = None
        for c in columns:
            val = str(data[0].get(c, '') or '')
            if re.match(r'\d{4}-\d{2}-\d{2}', val):
                date_col = c
                break
        if not date_col:
            return None
        dates = [str(row.get(date_col, ''))[:10] for row in data if row.get(date_col)]
        dates = [d for d in dates if re.match(r'\d{4}-\d{2}-\d{2}', d)]
        if not dates:
            return None
        min_d, max_d = min(dates), max(dates)
        if min_d == max_d:
            return min_d
        return f"{min_d} ~ {max_d}"

    def _validate_sql(self, sql, question):
        """Layer A: Validate SQL quality before execution. Returns (is_valid, fixed_sql_or_None)."""
        prompt = f"""你是一个SQL审查员。检查以下Databricks SQL是否正确。

已知表结构要点：
- 主表：gbis.biz.ads_kpi_summary_daily，字段包括：date, brand, country, second_region_name, client_type, gross_deposit, withdrawal, net_deposit, risk_free_revenue, front_end_ecost, front_end_ecost_daily_report, trading_volume, ftd_count, ftt_count, register_count, live_count, rt, equity, tdau, date_y, date_q
- brand取值：APAC, GS, VTJ, PU, STAR, MM, UM, VT
- second_region_name取值：Asia, Europe, LATAM, MENA, Others（用户说"地区/区域/region"时用此字段，而非country）
- 目标表：gbis.biz.dim_kpi_target（字段：brand, date_q, nrfr_target_b, nrfr_target_a）
- 目标表中APAC和VTJ合并为brand='APAC + VTJ'，JOIN时主表必须CASE合并
- NDM = (net_deposit + rt) / gross_deposit
- NRFR = risk_free_revenue - front_end_ecost_daily_report

用户问题："{question}"

SQL：
```sql
{sql}
```

检查项（只关注明确错误，不做风格优化）：
1. SELECT中的字段名是否在上述已知字段列表中存在（最重要！编造的字段一定会报错）
2. 表名是否正确
3. WHERE日期格式必须是YYYY-MM-DD
4. GROUP BY是否匹配SELECT中的非聚合列
5. 如果SQL引用了dim_kpi_target.date_q，检查过滤/JOIN条件中date_q的类型是否匹配——date_q是字符串格式（如'2026_Q2'），不能直接跟QUARTER()返回的整数比较，需要构造成相同字符串格式

重要：如果SQL语法和字段名都正确，即使你觉得可以优化也必须输出VALID。只有在确定会导致执行报错时才输出FIX。

如果SQL正确，只输出：VALID
如果有明确错误会导致执行失败，输出：FIX，然后另起一行输出修正后的完整SQL（用```sql包裹）"""

        try:
            result = self._call_haiku(prompt)
            if result.strip().startswith('VALID'):
                return True, None
            if 'FIX' in result:
                fixed = re.search(r'```sql\s*\n(.*?)\n```', result, re.DOTALL)
                if fixed:
                    return False, fixed.group(1).strip()
            return True, None
        except Exception as e:
            print(f'[SQL Validate] Error: {e}')
            return True, None

    def _validate_data(self, data, question, sql):
        """Layer B: Validate data quality after execution. Returns (is_valid, issue_description)."""
        if not data or len(data) == 0:
            return True, None

        sample = data[:10] if len(data) > 10 else data
        columns = list(data[0].keys())

        prompt = f"""你是一个数据质量审查员。检查以下查询结果是否合理。

用户问题："{question}"
执行的SQL概要：{sql[:200]}...
返回行数：{len(data)}
列名：{columns}
数据样本（前10行）：
{json.dumps(sample, default=str, ensure_ascii=False)}

检查项：
1. 数据量级是否合理（金额不应出现明显异常值，如某品牌突然为0或比其他大1000倍）
2. 是否有全NULL列或明显脏数据
3. 数值是否在合理范围（NRFR/入金出金通常在几万到几千万美元级别，NDM在0-100%之间，TDAU在几百到几千）
4. 日期范围是否符合问题要求

重要：不要建议添加额外列（如百分比、环比等），只检查现有数据质量。

如果数据合理，只输出：VALID
如果有问题，输出：ISSUE: 具体问题描述（一句话）
如果建议补充一条SQL来优化输出（如加百分比列），输出：SUGGEST_SQL，然后另起一行输出补充SQL（用```sql包裹）"""

        try:
            result = self._call_haiku(prompt)
            if result.strip().startswith('VALID'):
                return True, None
            if 'SUGGEST_SQL' in result:
                suggested = re.search(r'```sql\s*\n(.*?)\n```', result, re.DOTALL)
                if suggested:
                    return False, ('suggest_sql', suggested.group(1).strip())
            if 'ISSUE' in result:
                issue = result.split('ISSUE:')[-1].strip()
                return False, ('issue', issue)
            return True, None
        except Exception as e:
            print(f'[Data Validate] Error: {e}')
            return True, None

    def _is_english(self, text):
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
        return chinese_chars == 0

    def chat(self, message, history=None):
        from datetime import date
        today = date.today().isoformat()
        user_lang_en = self._is_english(message)

        system_prompt = f"""你是GBIS集团的高管商业智能助手。面向C-level高管，给出简洁、有结论、有图表的数据分析。

# 基本信息
- 今天：{today}
- 品牌（8个）：APAC, GS, VTJ, PU, STAR, MM, UM, VT
- 语言：严格跟随用户语言。用户用英文提问必须全英文回答（包括分析结论、图表标题、建议问题），用户用中文提问则中文回答
- 时间口径：中文用（环比/同比/本季度至今），英文用（MoM/YoY/QTD）。指标缩写直接用（NRFR/NDM/RFR/TDAU/FTD）
- 使用QTD/YTD时加括号解释：QTD（本季度累计）、YTD（本年累计）
- 术语：withdrawal统一叫"出金"（不叫提款/提现），deposit叫"入金"
- 术语：risk_free_revenue叫"RFR"（不叫GRFR），即 RFR = risk_free_revenue
- NRFR = risk_free_revenue - front_end_ecost_daily_report。因为front_end_ecost_daily_report是预估值，所以NRFR必须标注为"NRFR (est.)"或"NRFR（预估）"

# SQL 规则
1. 输出格式：只用 ```sql 代码块，可以输出多条，系统会依次执行并合并结果
2. 用户提到N个品牌就必须查N个品牌（WHERE brand IN (...)），绝不能只查其中一个而遗漏另一个；用户只提到1个品牌就只查1个品牌，绝不能自动添加其他品牌做对比
3. 月度趋势必须 GROUP BY DATE_TRUNC('MONTH', date)，禁止返回日粒度画趋势线
4. 日粒度仅用于：每日累计进度、单日异常定位
5. Top/集中度分析：只取覆盖80%的头部（Top 5-10），图表不超过10个类别
6. JOIN 必须用表别名限定所有列（防止 AMBIGUOUS_REFERENCE）
7. 计算字段必须显式写出（如 nrfr_target_b_qtd = t2.nrfr_target_b * t3.quarter_progress）
8. 严格按知识库中每张表的字段名写SQL，不同表同一指标列名可能不同
9. 数据范围：
   - 问特定月份 → 查该月
   - 问"本月"/"当月"/"这个月" → 查当月（DATE_TRUNC('MONTH', CURRENT_DATE()) 至今），回答中必须标注具体月份（如"2026年5月"）
   - 问趋势/变化 → 拉12个月到最新完整月，上界 `date < DATE_TRUNC('MONTH', CURRENT_DATE())`
   - 问排名/贡献/占比（无指定时间）→ 默认过去12个完整月，回答和图表标题必须标注时间范围（如"近12个月"）
10. 禁止在SELECT中直接输出 user_id/account_id/client_id/email/phone 等明细字段。但允许在JOIN/WHERE/GROUP BY中使用user_id做聚合分析（如COUNT(DISTINCT user_id)）
11. 分析"目标完成度排名/对比"时，SQL SELECT必须包含完成度百分比列（如 ROUND(actual/target*100,1) AS completion_pct），不要只输出绝对值。图表直接展示百分比排名才有意义。可以同时保留绝对值列用于文字分析，但百分比列必须存在
13. SQL SELECT只输出问题需要的列。问绝对值（如"RFR是多少"）就只输出金额列，不要额外加百分比/环比列；问百分比/完成度才输出百分比列。多余的列会干扰图表展示
12. JOIN dim_kpi_target表时：
    - 必须在一条SQL里完成JOIN，禁止拆成多条SQL分别查再拼接
    - 必须先用CASE合并APAC和VTJ：`CASE WHEN brand IN ('APAC','VTJ') THEN 'APAC + VTJ' ELSE brand END AS brand`
    - date_q是字符串格式（如'2026_Q2'），匹配时注意类型一致：可通过主表date_q列直接JOIN，或用CONCAT(YEAR(CURRENT_DATE()),'_Q',QUARTER(CURRENT_DATE()))构造字符串
    - 非目标相关查询APAC和VTJ正常分开。回答中标注"APAC含VTJ"

# 表刷新容错
- `ads_kpi_summary_daily` 每天14:00-14:10(UTC+8)刷新，期间可能为空
- 0行时改用品牌dashboard表：STAR→dashboard_star_sales_metrics_daily, GS→dashboard_gs_sales_metrics_daily, APAC/VTJ→dashboard_apac_vtj_sales_metrics_daily, PU→dashboard_pu_user_metrics_daily, UM→dashboard_um_user_metrics_daily
- dashboard表已按品牌过滤，不需要 WHERE brand

# 回答风格
- 需要查数据时直接输出 ```sql 代码块，禁止输出"我先拉取…""让我查一下…"等计划性陈述
- 回答深度匹配问题深度：问"表现如何"→ 展示数据排名即可；明确问"为什么"→ 才拆解原因
- 结论先行，一句话判断
- 长度自适应：简单问题2句话，拆解可以更长，文本不超200字
- 绝对不展示SQL，不解释方法论
- 末尾输出跟进建议：```suggestions ["问题1","问题2","问题3"] ```
- 跟进建议规则：
  - 必须是当前数据库能回答的问题（基于已有表和字段）
  - 只涉及内部数据，不能推荐外部市场/竞品问题
  - 紧扣当前话题深入或同维度拓展，不要太发散
  - 示例：问了NRFR → 建议拆解NRFR的国家/品牌维度，或对比目标，不要跳到完全无关的指标

# 图表
- 图表由系统自动生成，不需要你输出任何chart配置
- 唯一例外：目标完成度分析时输出4个进度条（固定格式，不多不少）：
  - 2个当前完成度：actual_qtd / target_full_quarter（展示目前在整个季度目标中的位置）
  - 2个季末预测完成度：(actual_qtd / quarter_progress) / target_full_quarter（按当前速度线性外推到季末）
```chart
{{"type": "progress", "items": [{{"label": "B级目标 当前", "current": actual_qtd, "target": target_b}}, {{"label": "A级目标 当前", "current": actual_qtd, "target": target_a}}, {{"label": "B级目标 季末预测", "current": round(actual_qtd/quarter_progress), "target": target_b}}, {{"label": "A级目标 季末预测", "current": round(actual_qtd/quarter_progress), "target": target_a}}]}}
```

# 业务知识
- NDM = (net_deposit + rt) / gross_deposit
- 拆解NDM只看 gross_deposit 和 withdrawal，不看 net_deposit（无业务意义）
- 新客定义：ftd_date在当月的用户即为新客（当月首次入金）。老客：ftd_date在当月之前
- 新客/老客分析使用 platinum.gbis.dws_login_metrics_daily（此表自带ftd_date字段，无需JOIN其他表）
- 注意：platinum表没有rt列！NDM在platinum表中简化为 net_deposit/gross_deposit（不加rt）
- 示例SQL：SELECT CASE WHEN ftd_date >= DATE_TRUNC('MONTH', CURRENT_DATE()) THEN '新客' ELSE '老客' END AS cohort, COUNT(DISTINCT user_id) AS users, SUM(gross_deposit) AS deposit, ABS(SUM(withdraw)) AS withdrawal FROM platinum.gbis.dws_login_metrics_daily WHERE date >= DATE_TRUNC('MONTH', CURRENT_DATE()) AND brand = 'XX' AND ftd_date IS NOT NULL GROUP BY 1
- 分析NDM聚集性/分布时，SQL直接按维度计算NDM值（不是展示入金出金明细）
- 分析维度优先级：地区(second_region_name) > 国家(country) > 客户类型(client_type)
- 用户问"按地区/区域/region分组"→ 使用second_region_name字段（只有4个值：Asia/Europe/LATAM/MENA），绝不用country
- NRFR目标对比参照知识库中示例SQL，必须同时给出Target A和Target B
- 季末预测计算：quarter_progress直接用这个SQL片段作为子查询计算，不要自己发明其他写法：`DATEDIFF(MAX(t1.date), DATE_TRUNC('QUARTER', MAX(t1.date))) / DATEDIFF(ADD_MONTHS(DATE_TRUNC('QUARTER', MAX(t1.date)), 3), DATE_TRUNC('QUARTER', MAX(t1.date))) AS quarter_progress`。季末预测 = actual_qtd / quarter_progress

# 边界
- 只回答GBIS数据相关问题
- 用户问用户明细 → "抱歉，当前没有用户明细数据的查询权限，仅支持聚合维度分析。"
- 无法确认 → "这个我无法确认，BI团队会跟进。"

# 知识库
{self.knowledge_base}
"""
        messages = []
        if history:
            messages = self._build_context(history, system_prompt)
        messages.append({'role': 'user', 'content': message})

        response_text = self._call_llm(system_prompt, messages)

        sql_queries = self._extract_sql(response_text)

        if sql_queries:
            if isinstance(sql_queries, str):
                sql_queries = [sql_queries]

            all_data = []
            all_sqls = []
            for sq in sql_queries:
                # Layer A: SQL quality check
                is_valid, fixed_sql = self._validate_sql(sq, message)
                if not is_valid and fixed_sql:
                    print(f'[SQL Validate] Fixed SQL applied')
                    sq = fixed_sql

                result = self._execute_sql(sq)
                if result['success'] and len(result['data']) > 0:
                    all_data.extend(result['data'])
                    all_sqls.append(sq)

            if len(all_data) > 0:
                mentioned_brands = self._extract_mentioned_brands(message)
                missing_brands = self._check_brand_coverage(mentioned_brands, all_data)
                if missing_brands:
                    messages.append({'role': 'assistant', 'content': response_text})
                    messages.append({
                        'role': 'user',
                        'content': f'查询结果中缺少以下品牌的数据：{", ".join(missing_brands)}。请补充查询这些品牌的相同指标，用 WHERE brand IN ({", ".join(repr(b) for b in missing_brands)}) 输出 ```sql 代码块。'
                    })
                    fix_response = self._call_llm(system_prompt, messages)
                    fix_sql = self._extract_sql(fix_response)
                    if fix_sql:
                        if isinstance(fix_sql, str):
                            fix_sql = [fix_sql]
                        for sq in fix_sql:
                            r = self._execute_sql(sq)
                            if r['success'] and len(r['data']) > 0:
                                all_data.extend(r['data'])
                                all_sqls.append(sq)
                    messages.append({'role': 'assistant', 'content': fix_response})
                else:
                    messages.append({'role': 'assistant', 'content': response_text})

                # Layer B: Data quality validation
                data_valid, data_issue = self._validate_data(all_data, message, all_sqls[-1] if all_sqls else '')
                if not data_valid and data_issue:
                    issue_type, issue_detail = data_issue
                    if issue_type == 'issue':
                        print(f'[Data Validate] Issue detected: {issue_detail}')

                messages.append({
                    'role': 'user',
                    'content': f"""查询结果（{len(all_data)}行）：
{json.dumps(all_data, default=str, ensure_ascii=False)}

{"Provide an executive-level answer in English:" if user_lang_en else "请给出高管级别的回答："}
1. {"One-sentence conclusion" if user_lang_en else "一句话结论"}
2. {"2-3 key data points" if user_lang_en else "2-3个关键数字要点"}
3. {"A ```suggestions block with 3 valuable follow-up questions (in English)" if user_lang_en else "一个 ```suggestions 块，包含3个有价值的跟进问题"}

{"Do not show SQL. Do not explain methodology. Charts are auto-generated." if user_lang_en else "不要展示SQL。不要解释方法论。图表由系统自动生成，不需要你输出。"}"""
                })
                final_response = self._call_llm(system_prompt, messages)
                progress_chart = self._extract_chart(final_response)
                if progress_chart:
                    chart_config = self._fix_progress_forecast(progress_chart)
                else:
                    chart_config = self._decide_chart(all_data, message, user_lang_en)
                suggestions = self._extract_suggestions(final_response)
                clean_response = self._clean_response(final_response)
                return {
                    'answer': clean_response,
                    'sql': all_sqls[0] if len(all_sqls) == 1 else all_sqls,
                    'data': all_data,
                    'chart': chart_config,
                    'suggestions': suggestions
                }
            else:
                messages.append({'role': 'assistant', 'content': response_text})
                messages.append({
                    'role': 'user',
                    'content': '上一个查询返回了0行数据，可能是表正在刷新。请使用知识库中的备选 dashboard 表重新写SQL查询，然后直接输出新的 ```sql 代码块。'
                })
                retry_response = self._call_llm(system_prompt, messages)
                retry_sql = self._extract_sql(retry_response)
                if retry_sql:
                    if isinstance(retry_sql, str):
                        retry_sql = [retry_sql]
                    retry_data = []
                    for sq in retry_sql:
                        r = self._execute_sql(sq)
                        if r['success']:
                            retry_data.extend(r['data'])
                    if len(retry_data) > 0:
                        messages.append({'role': 'assistant', 'content': retry_response})
                        messages.append({
                            'role': 'user',
                            'content': f"""查询结果（{len(retry_data)}行）：
{json.dumps(retry_data, default=str, ensure_ascii=False)}

{"Provide an executive-level answer in English:" if user_lang_en else "请给出高管级别的回答："}
1. {"One-sentence conclusion" if user_lang_en else "一句话结论"}
2. {"2-3 key data points" if user_lang_en else "2-3个关键数字要点"}
3. {"A ```suggestions block with 3 valuable follow-up questions (in English)" if user_lang_en else "一个 ```suggestions 块，包含3个有价值的跟进问题"}

{"Do not show SQL. Do not explain methodology. Charts are auto-generated." if user_lang_en else "不要展示SQL。不要解释方法论。图表由系统自动生成，不需要你输出。"}"""
                        })
                        final_response = self._call_llm(system_prompt, messages)
                        progress_chart = self._extract_chart(final_response)
                        if progress_chart:
                            chart_config = progress_chart
                        else:
                            chart_config = self._decide_chart(retry_data, message, user_lang_en)
                        suggestions = self._extract_suggestions(final_response)
                        clean_response = self._clean_response(final_response)
                        return {
                            'answer': clean_response,
                            'sql': retry_sql,
                            'data': retry_data,
                            'chart': chart_config,
                            'suggestions': suggestions
                        }
                return {
                    'answer': '数据正在刷新中，请稍后再试（约14:10后恢复）。',
                    'sql': sql_queries,
                    'data': None,
                    'chart': None
                }

        chart_config = self._extract_chart(response_text)  # progress bars only
        suggestions = self._extract_suggestions(response_text)
        clean_response = self._clean_response(response_text)
        return {'answer': clean_response, 'sql': None, 'data': None, 'chart': chart_config, 'suggestions': suggestions}

    def _extract_sql(self, text):
        all_sqls = []
        for pattern in [r'```sql\s*\n(.*?)\n```', r'```\s*\n(SELECT.*?)\n```']:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            for m in matches:
                sql = m.strip()
                if sql.upper().startswith('SELECT') or sql.upper().startswith('WITH'):
                    if sql not in all_sqls:
                        all_sqls.append(sql)
        if len(all_sqls) == 0:
            return None
        if len(all_sqls) == 1:
            return all_sqls[0]
        return all_sqls

    # Column name → Chinese label mapping for titles
    _COL_LABELS = {
        'gross_deposit': '入金', 'net_deposit': '净入金', 'withdrawal': '出金',
        'total_withdrawal': '出金', 'total_gross_deposit': '入金', 'total_net_deposit': '净入金',
        'ndm': 'NDM', 'nrfr': 'NRFR', 'rfr': 'RFR', 'grfr': 'RFR',
        'tdau': 'TDAU', 'ftd_count': 'FTD', 'ftt_count': 'FTT', 'register_count': '注册数', 'live_count': 'Live数',
        'trading_volume': '交易量', 'risk_free_revenue': 'RFR',
        'spread_revenue': 'Spread收入', 'commission_revenue': '佣金收入',
        'front_end_ecost': '前端成本', 'equity': '净值',
        'total_ndm': 'NDM', 'total_nrfr': 'NRFR', 'total_grfr': 'RFR',
        'total_tdau': 'TDAU', 'avg_tdau': 'TDAU',
    }

    def _generate_chart_config(self, data, question, answer, is_en=None):
        """Rule-based chart configuration — no LLM, 100% deterministic."""
        if is_en is None:
            is_en = self._is_english(question)
        if not data or len(data) <= 1:
            return None

        # Filter out rows with null/undefined category values
        data = [row for row in data if all(
            row.get(k) is not None and str(row.get(k, '')).lower() not in ('none', 'null', 'undefined', '')
            for k in row.keys() if not isinstance(row.get(k), (int, float))
        )]
        if not data or len(data) <= 1:
            return None

        columns = list(data[0].keys())

        # Classify columns
        date_cols = []
        numeric_cols = []
        category_cols = []
        for c in columns:
            val = data[0].get(c)
            if isinstance(val, (int, float)):
                numeric_cols.append(c)
            elif re.match(r'\d{4}-\d{2}', str(val or '')) or re.match(r'\w{3},?\s+\d', str(val or '')):
                date_cols.append(c)
            else:
                category_cols.append(c)

        if not numeric_cols:
            return None

        # Count unique values
        def unique_count(col):
            return len(set(str(row.get(col, '')) for row in data))

        # Pick the primary numeric column — prefer meaningful metrics for chart
        skip_keywords = ('dow', 'day_of_week', 'dayofweek', 'weekday', 'month_num', 'year', 'week_num', 'row_num', 'rank')
        numeric_cols = [c for c in numeric_cols if not any(k in c.lower() for k in skip_keywords)]
        if not numeric_cols:
            return None
        pct_keywords = ('pct', 'percent', 'completion', 'rate', 'ratio')
        metric_keywords = ('volume', 'revenue', 'count', 'amount', 'deposit', 'total', 'sum')
        pct_cols = [c for c in numeric_cols if any(k in c.lower() for k in pct_keywords)]
        metric_cols = [c for c in numeric_cols if any(k in c.lower() for k in metric_keywords)]
        y_col = pct_cols[0] if pct_cols else (metric_cols[0] if metric_cols else numeric_cols[0])

        # === Pattern 1: Time-series (has date column with multiple dates) ===
        if date_cols:
            date_col = date_cols[0]
            n_dates = unique_count(date_col)
            if n_dates >= 3:
                # Find a category column for color (brand, client_type, etc.) with 2-10 groups
                color_col = None
                for cc in category_cols:
                    uc = unique_count(cc)
                    if 2 <= uc <= 10:
                        color_col = cc
                        break

                label = self._COL_LABELS.get(y_col, y_col)
                if is_en:
                    title = f'{label} Trend (by {color_col})' if color_col else f'{label} Trend'
                else:
                    title = f'{label}趋势（按{color_col}）' if color_col else f'{label}趋势'

                return [{'type': 'line', 'title': title, 'x': date_col, 'y': y_col, 'color': color_col}]

        # === Pattern 2: Category comparison (no date, has category) ===
        if category_cols:
            x_col = category_cols[0]
            n_cats = unique_count(x_col)

            # Too many categories or only 1 → not suitable for chart
            if n_cats > 15 or n_cats < 2:
                return None

            # Find best x (most categories) and group_col (fewest, for splitting)
            # Sort category cols: the one with more unique values is better as x-axis
            cat_info = [(cc, unique_count(cc)) for cc in category_cols]
            cat_info.sort(key=lambda t: t[1], reverse=True)

            x_col = cat_info[0][0]
            n_cats = cat_info[0][1]
            group_col = None  # for filter/color
            if len(cat_info) > 1 and cat_info[-1][1] <= 5:
                group_col = cat_info[-1][0]

            if n_cats > 15 or n_cats < 2:
                return None

            label = self._COL_LABELS.get(y_col, y_col)

            if group_col:
                n_groups = unique_count(group_col)
                groups = list(set(str(row.get(group_col, '')) for row in data))
                if n_groups <= 3:
                    # Few groups → split into separate charts
                    charts = []
                    for g in sorted(groups):
                        charts.append({
                            'type': 'bar',
                            'title': f'{g} {label}',
                            'x': x_col, 'y': y_col,
                            'filter': {'column': group_col, 'value': g}
                        })
                    return charts[:3]
                else:
                    # More groups → use as color
                    title = f'{label} Comparison' if is_en else f'{label}对比'
                    return [{'type': 'bar', 'title': title, 'x': x_col, 'y': y_col, 'color': group_col}]
            else:
                if is_en:
                    title = f'{label} Ranking' if n_cats > 5 else f'{label} Comparison'
                else:
                    title = f'{label}排名' if n_cats > 5 else f'{label}对比'
                return [{'type': 'bar', 'title': title, 'x': x_col, 'y': y_col}]

        # === Pattern 3: Only numeric columns, no useful category ===
        return None

    def _fix_progress_forecast(self, chart):
        """Recalculate forecast values in progress charts using correct quarter_progress."""
        if not chart or not isinstance(chart, dict) or chart.get('type') != 'progress':
            return chart
        items = chart.get('items', [])
        if len(items) != 4:
            return chart

        # items[0],[1] = current; items[2],[3] = forecast
        # Get actual QTD from current items (same value for both)
        actual_qtd = items[0].get('current', 0)
        if actual_qtd <= 0:
            return chart

        # Calculate correct quarter_progress using DB
        try:
            result = self._execute_sql(
                "SELECT DATEDIFF(MAX(date), DATE_TRUNC('QUARTER', MAX(date))) / "
                "DATEDIFF(ADD_MONTHS(DATE_TRUNC('QUARTER', MAX(date)), 3), DATE_TRUNC('QUARTER', MAX(date))) "
                "AS qp FROM gbis.biz.ads_kpi_summary_daily WHERE date >= DATE_TRUNC('QUARTER', CURRENT_DATE())"
            )
            if result['success'] and result['data']:
                qp = result['data'][0]['qp']
                if qp and qp > 0:
                    correct_forecast = round(actual_qtd / qp)
                    items[2]['current'] = correct_forecast
                    items[3]['current'] = correct_forecast
        except Exception as e:
            print(f'[ChatEngine] Fix progress forecast error: {e}')
        return chart

    def _extract_chart(self, text):
        """Only extract progress bar configs from AI response."""
        matches = re.findall(r'```chart\s*\n(.*?)\n```', text, re.DOTALL)
        charts = []
        for m in matches:
            try:
                c = json.loads(m.strip())
                if c.get('type') == 'progress':
                    charts.append(c)
            except json.JSONDecodeError:
                pass
        if len(charts) == 0:
            return None
        if len(charts) == 1:
            return charts[0]
        return charts

    def _extract_suggestions(self, text):
        match = re.search(r'```suggestions\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                return None
        return None

    def _clean_response(self, text):
        text = re.sub(r'```chart\s*\n.*?\n```', '', text, flags=re.DOTALL)
        text = re.sub(r'```suggestions\s*\n.*?\n```', '', text, flags=re.DOTALL)
        text = re.sub(r'```sql\s*\n.*?\n```', '', text, flags=re.DOTALL)
        return text.strip()


def load_conversations():
    if os.path.exists(CONVERSATIONS_FILE):
        try:
            with open(CONVERSATIONS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_conversations(conversations):
    with open(CONVERSATIONS_FILE, 'w') as f:
        json.dump(conversations, f, ensure_ascii=False, default=str)
