let currentConversationId = null;
let isLoading = false;
const BASE = typeof API_BASE !== 'undefined' ? API_BASE : '/gbis-analysis/chat';

function newConversation() {
    currentConversationId = null;
    document.getElementById('messages').innerHTML = '';
    document.getElementById('messagesContainer').classList.remove('active');
    document.getElementById('welcomeScreen').style.display = 'flex';
    document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
}

function sendSuggestion(text) {
    document.getElementById('messageInput').value = text;
    sendMessage();
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    if (!message || isLoading) return;

    document.getElementById('welcomeScreen').style.display = 'none';
    document.getElementById('messagesContainer').classList.add('active');

    appendMessage('user', message);
    input.value = '';
    input.style.height = 'auto';

    isLoading = true;
    document.getElementById('sendBtn').disabled = true;
    const loadingEl = appendThinking();

    try {
        const response = await fetch(BASE + '/api/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                conversation_id: currentConversationId
            })
        });

        if (response.redirected || response.url.includes('/login')) {
            window.location.href = response.url;
            return;
        }

        const data = await response.json();

        if (response.ok) {
            currentConversationId = data.conversation_id;
            appendMessage('assistant', data.answer, data.sql, data.data, data.chart, data.suggestions);
            loadConversations();
        } else if (response.status === 401) {
            const prefix = window.location.pathname.split('/hub')[0];
            window.location.href = prefix + '/hub/login';
            return;
        } else {
            appendMessage('assistant', 'Error: ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        appendMessage('assistant', 'Connection error. Please try again.');
    } finally {
        loadingEl.remove();
        isLoading = false;
        document.getElementById('sendBtn').disabled = false;
    }
}

function appendMessage(role, content, sql, data, chart, suggestions) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;

    const avatar = role === 'user' ? 'K' : 'G';
    let html = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <div class="message-text">${formatMarkdown(content)}</div>
    `;

    // Render chart(s) if available
    if (chart) {
        const charts = Array.isArray(chart) ? chart : [chart];
        charts.forEach(c => {
            if (c.type === 'progress' && c.items) {
                html += renderProgressBars(c.items);
            } else if (data && data.length > 0) {
                let chartData = data;
                if (c.filter) {
                    chartData = data.filter(row => row[c.filter.column] === c.filter.value);
                }
                if (chartData.length > 0) {
                    const chartId = 'chart-' + Date.now() + '-' + Math.random().toString(36).substr(2, 8);
                    html += `<div class="chart-container" id="${chartId}"></div>`;
                    const _id = chartId, _c = c, _d = chartData;
                    requestAnimationFrame(() => requestAnimationFrame(() => renderChart(_id, _c, _d)));
                }
            }
        });
    }

    // Render data table only if no chart
    if (data && data.length > 0 && !chart) {
        html += renderDataTable(data);
    }

    // Render follow-up suggestions
    if (suggestions && suggestions.length > 0) {
        html += '<div class="suggestions">';
        suggestions.forEach(s => {
            html += `<button class="suggestion-btn" onclick="sendSuggestion('${escapeHtml(s)}')">${escapeHtml(s)}</button>`;
        });
        html += '</div>';
    }

    // Feedback buttons for assistant messages
    if (role === 'assistant') {
        const fbId = 'fb-' + Date.now() + '-' + Math.random().toString(36).substr(2, 6);
        const lang = getUILang();
        const fbLabel = lang === 'en' ? 'How was this response?' : '你觉得这个回答如何？';
        html += `<div class="feedback-section" id="${fbId}">
            <span class="feedback-label">${fbLabel}</span>
            <button class="feedback-btn" onclick="sendFeedback('${fbId}', 'good')">👍</button>
            <button class="feedback-btn" onclick="sendFeedback('${fbId}', 'bad')">👎</button>
        </div>`;
    }

    html += '</div>';
    div.innerHTML = html;
    container.appendChild(div);
    scrollToBottom();
}

function renderChart(containerId, config, data) {
    const container = document.getElementById(containerId);
    if (!container || !data || data.length === 0) return;

    // Coerce numeric strings back to numbers (JSON roundtrip may stringify them)
    data = data.map(row => {
        const r = {...row};
        for (const k of Object.keys(r)) {
            if (typeof r[k] === 'string' && r[k] !== '' && !isNaN(Number(r[k])) && !/^\d{4}-/.test(r[k])) {
                r[k] = Number(r[k]);
            }
        }
        return r;
    });

    const type = config.type || 'bar';
    const columns = Object.keys(data[0]);
    const numericCols = columns.filter(c => typeof data[0][c] === 'number');
    const nonNumericCols = columns.filter(c => typeof data[0][c] !== 'number');

    const resolveCol = (key) => {
        if (!key) return null;
        if (columns.includes(key)) return key;
        const lower = key.toLowerCase();
        return columns.find(c => c.toLowerCase() === lower) || columns.find(c => c.toLowerCase().includes(lower)) || null;
    };

    let xKey = resolveCol(config.x) || nonNumericCols[0] || columns[0];
    let yKey = resolveCol(config.y);
    let colorKey = resolveCol(config.color);
    const title = config.title || '';

    let traces = [];
    const colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880'];

    if (colorKey && type !== 'pie') {
        if (!yKey) yKey = numericCols[0];
        const sortedData = [...data].sort((a, b) => String(a[xKey]).localeCompare(String(b[xKey])));
        const groups = {};
        sortedData.forEach(row => {
            const group = row[colorKey] || 'Other';
            if (!groups[group]) groups[group] = { x: [], y: [] };
            groups[group].x.push(row[xKey]);
            groups[group].y.push(row[yKey]);
        });
        // If too many groups, keep top N by total value and merge rest into "其他"
        const maxGroups = 6;
        let entries = Object.entries(groups);
        if (entries.length > maxGroups) {
            const ranked = entries.map(([name, vals]) => ({
                name, vals, total: vals.y.reduce((s, v) => s + Math.abs(v || 0), 0)
            })).sort((a, b) => b.total - a.total);
            const topEntries = ranked.slice(0, maxGroups - 1);
            const otherEntries = ranked.slice(maxGroups - 1);
            // Merge others
            const otherGroup = { x: [], y: [] };
            otherEntries.forEach(e => {
                e.vals.x.forEach((xv, i) => {
                    const idx = otherGroup.x.indexOf(xv);
                    if (idx >= 0) { otherGroup.y[idx] += (e.vals.y[i] || 0); }
                    else { otherGroup.x.push(xv); otherGroup.y.push(e.vals.y[i] || 0); }
                });
            });
            entries = topEntries.map(e => [e.name, e.vals]);
            if (otherGroup.x.length > 0) entries.push(['其他', otherGroup]);
        }
        entries.forEach(([name, vals]) => {
            traces.push({
                x: vals.x,
                y: vals.y,
                name: name,
                type: type === 'line' ? 'scatter' : 'bar',
                mode: type === 'line' ? 'lines+markers' : undefined
            });
        });
    } else if (type === 'pie') {
        if (!yKey) yKey = numericCols[0];
        traces.push({
            labels: data.map(r => r[xKey]),
            values: data.map(r => r[yKey]),
            type: 'pie',
            hole: 0.4
        });
    } else {
        if (!yKey) yKey = numericCols[0];
        if (type === 'bar') {
            // Aggregate duplicate x values for clean bar chart
            const agg = {};
            data.forEach(r => {
                const key = String(r[xKey]);
                agg[key] = (agg[key] || 0) + (Number(r[yKey]) || 0);
            });
            const xArr = Object.keys(agg);
            const yArr = Object.values(agg);
            traces.push({
                x: xArr, y: yArr, type: 'bar',
                marker: { color: xArr.map((_, i) => colors[i % colors.length]) }
            });
        } else {
            const sorted = [...data].sort((a, b) => String(a[xKey]).localeCompare(String(b[xKey])));
            traces.push({
                x: sorted.map(r => r[xKey]),
                y: sorted.map(r => r[yKey]),
                type: 'scatter',
                mode: 'lines+markers',
                line: { color: '#636EFA' }
            });
        }
    }

    let xaxisConfig = { gridcolor: '#e9ecef', linecolor: '#e9ecef' };
    const xVals = data.map(r => r[xKey]);
    // Detect date-like values in multiple formats
    const isDateLike = xVals.length > 1 && xVals.every(v => {
        const s = String(v);
        return /^\d{4}-\d{2}-\d{2}/.test(s) || /^\w{3},?\s+\d{1,2}\s+\w+\s+\d{4}/.test(s) || !isNaN(Date.parse(s));
    });
    if (isDateLike) {
        // Normalize all x values to YYYY-MM-DD
        traces.forEach(t => {
            if (t.x) t.x = t.x.map(v => {
                const d = new Date(v);
                if (!isNaN(d)) return d.toISOString().substring(0, 10);
                return String(v).substring(0, 10);
            });
        });
        const normalizedX = traces[0]?.x || [];
        const isMonthly = normalizedX.every(v => v.endsWith('-01'));
        if (isMonthly) {
            xaxisConfig.dtick = 'M1';
            xaxisConfig.tickformat = '%b %Y';
        } else {
            xaxisConfig.tickformat = '%m/%d';
        }
    }

    const layout = {
        title: { text: title, font: { size: 14, color: '#1a1a2e' } },
        font: { family: 'Inter, sans-serif', size: 11, color: '#495057' },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        margin: { t: 40, r: 20, b: 80, l: 60 },
        height: 340,
        xaxis: xaxisConfig,
        yaxis: { gridcolor: '#e9ecef', linecolor: '#e9ecef' },
        legend: { orientation: 'h', y: -0.25, xanchor: 'center', x: 0.5 },
        barmode: traces.length > 1 && type === 'bar' ? 'stack' : 'group',
        bargap: 0.3
    };

    Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
}

function getUILang() {
    const toggle = document.querySelector('.lang-toggle button.active');
    if (toggle) return toggle.textContent.trim() === 'EN' ? 'en' : 'zh';
    return (typeof localStorage !== 'undefined' && localStorage.getItem('hub_lang')) || 'zh';
}

function appendThinking() {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = 'loading-message';

    const lang = getUILang();
    const stepsMap = {
        zh: ['正在理解问题...', '正在查询数据库...', '正在分析数据...', '即将输出结论...'],
        en: ['Understanding your question...', 'Querying database...', 'Analyzing data...', 'Generating response...']
    };
    const steps = stepsMap[lang] || stepsMap.zh;

    div.innerHTML = `
        <div class="message-avatar">G</div>
        <div class="message-content thinking-content">
            <div class="thinking-single">
                <div class="step-dot"></div>
                <span id="thinking-text">${steps[0]}</span>
            </div>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();

    steps.slice(1).forEach((text, i) => {
        setTimeout(() => {
            const el = document.getElementById('thinking-text');
            if (el) el.textContent = text;
        }, (i + 1) * 3000);
    });

    return div;
}

function renderProgressBars(items) {
    let html = '<div class="progress-bars">';
    items.forEach(item => {
        const pct = Math.min((item.current / item.target) * 100, 100);
        const displayPct = ((item.current / item.target) * 100).toFixed(1);
        const currentStr = formatNumber(item.current);
        const targetStr = formatNumber(item.target);
        html += `
            <div class="progress-item">
                <div class="progress-header">
                    <span class="progress-label">${escapeHtml(item.label)}</span>
                    <span class="progress-pct">${displayPct}%</span>
                </div>
                <div class="progress-track">
                    <div class="progress-fill" style="width: ${pct}%"></div>
                </div>
                <div class="progress-footer">
                    <span>当前 ${currentStr}</span>
                    <span>目标 ${targetStr}</span>
                </div>
            </div>
        `;
    });
    html += '</div>';
    return html;
}

function toggleSql(id) {
    document.getElementById(id).classList.toggle('visible');
}

function renderDataTable(data) {
    if (!data || data.length === 0) return '';

    const columns = Object.keys(data[0]);
    let html = '<div class="data-table-wrapper"><table class="data-table"><thead><tr>';
    columns.forEach(col => {
        html += `<th>${escapeHtml(col)}</th>`;
    });
    html += '</tr></thead><tbody>';

    data.slice(0, 10).forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
            let val = row[col];
            if (val === null || val === undefined) val = '-';
            else if (typeof val === 'number') val = formatNumber(val);
            else val = String(val);
            html += `<td>${escapeHtml(val)}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    if (data.length > 10) {
        html += `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Showing 10 of ${data.length} rows</div>`;
    }
    return html;
}

function formatNumber(num) {
    if (Math.abs(num) >= 1000000) return '$' + (num / 1000000).toFixed(2) + 'M';
    if (Math.abs(num) >= 1000) return '$' + (num / 1000).toFixed(1) + 'K';
    if (Number.isInteger(num)) return num.toLocaleString();
    return num.toFixed(2);
}

function formatMarkdown(text) {
    let html = text;
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/^### (.+)$/gm, '<strong>$1</strong>');
    html = html.replace(/^## (.+)$/gm, '<strong>$1</strong>');

    // Markdown tables
    html = html.replace(/((?:^\|.+\|$\n?)+)/gm, function(tableBlock) {
        const rows = tableBlock.trim().split('\n').filter(r => r.trim());
        if (rows.length < 2) return tableBlock;
        // Check if second row is separator
        const isSep = /^\|[\s\-:| ]+\|$/.test(rows[1]);
        let startIdx = isSep ? 2 : 1;
        let headerRow = rows[0];

        const parseRow = r => r.split('|').slice(1, -1).map(c => c.trim());
        const headers = parseRow(headerRow);
        let tableHtml = '<table class="md-table"><thead><tr>' +
            headers.map(h => `<th>${h}</th>`).join('') +
            '</tr></thead><tbody>';
        for (let i = startIdx; i < rows.length; i++) {
            const cells = parseRow(rows[i]);
            tableHtml += '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
        }
        tableHtml += '</tbody></table>';
        return tableHtml;
    });

    html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');
    html = html.replace(/<\/ul>\s*<ul>/g, '');
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    if (!html.startsWith('<')) html = '<p>' + html + '</p>';
    return html;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    container.scrollTop = container.scrollHeight;
}

async function loadConversations() {
    try {
        const response = await fetch(BASE + '/api/conversations');
        const data = await response.json();
        const list = document.getElementById('conversationList');
        list.innerHTML = '';
        data.forEach(conv => {
            const div = document.createElement('div');
            div.className = 'conv-item' + (conv.id === currentConversationId ? ' active' : '');
            if (manageMode) {
                const checked = selectedConversations.has(conv.id) ? 'checked' : '';
                div.innerHTML = `
                    <label class="conv-checkbox" onclick="event.stopPropagation()">
                        <input type="checkbox" ${checked} onchange="toggleSelect('${conv.id}', event)">
                    </label>
                    <span>${escapeHtml(conv.preview)}</span>
                `;
                div.onclick = (e) => toggleSelect(conv.id, e);
            } else {
                div.innerHTML = `
                    <span>${escapeHtml(conv.preview)}</span>
                    <button class="delete-btn" onclick="event.stopPropagation(); deleteConversation('${conv.id}')">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M4 4l6 6M10 4l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                        </svg>
                    </button>
                `;
                div.onclick = () => loadConversation(conv.id);
            }
            list.appendChild(div);
        });
    } catch (err) {}
}

async function loadConversation(id) {
    try {
        const response = await fetch(BASE + '/api/conversations/' + id);
        const msgs = await response.json();

        currentConversationId = id;
        document.getElementById('welcomeScreen').style.display = 'none';
        document.getElementById('messagesContainer').classList.add('active');
        document.getElementById('messages').innerHTML = '';

        msgs.forEach(msg => {
            appendMessage(msg.role, msg.content, msg.sql, msg.data, msg.chart);
        });

        document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
        loadConversations();
    } catch (err) {}
}

async function deleteConversation(id) {
    await fetch(BASE + '/api/conversations/' + id, { method: 'DELETE' });
    if (id === currentConversationId) newConversation();
    loadConversations();
}

let manageMode = false;
let selectedConversations = new Set();

function toggleManage() {
    manageMode = !manageMode;
    selectedConversations.clear();
    document.getElementById('manageBar').style.display = manageMode ? 'flex' : 'none';
    document.getElementById('manageBtn').style.display = manageMode ? 'none' : 'block';
    loadConversations();
}

function toggleSelect(id, e) {
    e.stopPropagation();
    if (selectedConversations.has(id)) {
        selectedConversations.delete(id);
    } else {
        selectedConversations.add(id);
    }
    loadConversations();
}

async function deleteSelected() {
    const ids = Array.from(selectedConversations);
    for (const id of ids) {
        await fetch(BASE + '/api/conversations/' + id, { method: 'DELETE' });
        if (id === currentConversationId) newConversation();
    }
    selectedConversations.clear();
    toggleManage();
    loadConversations();
}

async function sendFeedback(fbId, rating) {
    const section = document.getElementById(fbId);
    if (!section) return;
    const btns = section.querySelectorAll('.feedback-btn');
    btns.forEach(b => {
        b.disabled = true;
        if (b.textContent.trim() === (rating === 'good' ? '👍' : '👎')) {
            b.classList.add('selected');
        }
    });
    const lang = getUILang();
    const thanks = lang === 'en' ? 'Thanks for the feedback!' : '感谢反馈！';
    const label = section.querySelector('.feedback-label');
    if (label) label.textContent = thanks;
    label.classList.add('feedback-thanks');

    try {
        await fetch(BASE + '/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: currentConversationId,
                rating: rating
            })
        });
    } catch (err) {}
}

loadConversations();
document.getElementById('messageInput').focus();
