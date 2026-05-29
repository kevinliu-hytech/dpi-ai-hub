// Data Dashboard - Visual Analytics Interface

const BASE_PATH = document.querySelector('script[src*="dashboard.js"]')?.src.replace(/\/static\/js\/dashboard\.js.*/, '') || '';

function apiUrl(path) {
    return BASE_PATH + path;
}

// DOM Elements
const conversation = document.getElementById('conversation');
const dashboardInput = document.getElementById('dashboard-input');
const analyzeBtn = document.getElementById('analyze-btn');
const clearBtn = document.getElementById('clear-btn');
const sessionsBtn = document.getElementById('sessions-btn');
const languageToggle = document.getElementById('language-toggle');
const languageLabel = document.getElementById('language-label');
const btnText = analyzeBtn.querySelector('.btn-text');
const btnLoading = analyzeBtn.querySelector('.btn-loading');

// State
let chartHistory = [];
let currentLanguage = 'en';

// Session History
const MAX_SESSIONS = 5;
let savedSessions = JSON.parse(localStorage.getItem('dashboard_sessions') || '[]');
let currentSessionId = Date.now().toString();

// Event Listeners
analyzeBtn.addEventListener('click', performVisualization);
clearBtn.addEventListener('click', clearConversation);
languageToggle.addEventListener('click', toggleLanguage);
sessionsBtn.addEventListener('click', toggleSessionsPanel);

dashboardInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        performVisualization();
    }
});

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('example-btn')) {
        const question = e.target.getAttribute('data-question');
        dashboardInput.value = question;
        performVisualization();
    }
});

// Initialize
updateSessionsBadge();

// Main Visualization Function
async function performVisualization() {
    const question = dashboardInput.value.trim();
    if (!question) { alert('Please enter a question'); return; }

    analyzeBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'inline';
    dashboardInput.disabled = true;

    const welcomeMsg = document.querySelector('.welcome-message');
    if (welcomeMsg) welcomeMsg.remove();

    const loadingDiv = showLoading(question);

    try {
        const response = await fetch(apiUrl('/api/dashboard/visualize'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });

        const result = await response.json();
        loadingDiv.remove();

        if (result.success) {
            displayChart(question, result);
            chartHistory.push({ question, result, timestamp: new Date().toISOString() });
            saveCurrentSession();
            dashboardInput.value = '';
        } else {
            showError(result.error || 'Visualization failed');
        }
    } catch (error) {
        loadingDiv.remove();
        showError('Network error: ' + error.message);
    } finally {
        analyzeBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        dashboardInput.disabled = false;
        dashboardInput.focus();
    }
}

// Show Loading State
function showLoading(question) {
    const loadingHTML = `
        <div class="chart-block loading-chart">
            <div class="loading-spinner"></div>
            <p><strong>${escapeHtml(question)}</strong></p>
            <p style="margin-top: 10px; font-size: 13px; color: #86868b;">
                Generating query > Fetching data > Building chart...
            </p>
        </div>
    `;
    conversation.insertAdjacentHTML('beforeend', loadingHTML);
    conversation.scrollTop = conversation.scrollHeight;
    return conversation.lastElementChild;
}

// Display a Single Chart
function displayChart(question, result) {
    const chartId = `chart-${Date.now()}`;
    const meta = `${result.row_count} rows | ${result.chart_type} chart | ${result.execution_time.toFixed(2)}s`;

    const html = `
        <div class="chart-block">
            <div class="chart-header">
                <div class="chart-question">${escapeHtml(question)}</div>
                <div class="chart-meta">${meta}</div>
            </div>
            <div class="chart-body">
                <div id="${chartId}" style="width: 100%; height: 500px;"></div>
            </div>
            <div class="chart-actions">
                <button class="btn-export" onclick="exportChartToPDF(this)">Export PDF</button>
            </div>
        </div>
    `;

    conversation.insertAdjacentHTML('beforeend', html);

    setTimeout(() => {
        const container = document.getElementById(chartId);
        if (!container || !result.chart) return;

        const layout = Object.assign({}, result.chart.layout || {}, {
            paper_bgcolor: '#ffffff',
            plot_bgcolor: '#ffffff',
            font: { color: '#1d1d1f', size: 13 },
            xaxis: Object.assign({}, result.chart.layout?.xaxis || {}, {
                gridcolor: '#e8e8ed', zerolinecolor: '#d2d2d7'
            }),
            yaxis: Object.assign({}, result.chart.layout?.yaxis || {}, {
                gridcolor: '#e8e8ed', zerolinecolor: '#d2d2d7'
            }),
            legend: { font: { color: '#424245' } },
            margin: { t: 50, b: 60, l: 70, r: 30 }
        });

        Plotly.newPlot(container, result.chart.data, layout, {
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['lasso2d', 'select2d']
        });
    }, 100);

    conversation.scrollTop = conversation.scrollHeight;
}

// Show Error
function showError(message) {
    const errorHTML = `
        <div class="chart-block" style="border-left: 3px solid #f87171;">
            <div class="chart-body" style="padding: 24px;">
                <h3 style="color: #f87171; margin-bottom: 8px;">Error</h3>
                <p style="color: #6e6e73;">${escapeHtml(message)}</p>
            </div>
        </div>
    `;
    conversation.insertAdjacentHTML('beforeend', errorHTML);
    conversation.scrollTop = conversation.scrollHeight;
}

// Clear Conversation
function clearConversation() {
    if (confirm('Clear all charts?')) {
        if (chartHistory.length > 0) saveCurrentSession();
        conversation.innerHTML = `
            <div class="welcome-message">
                <h2>Ready for a new visualization</h2>
                <p>Ask me any question about your data</p>
            </div>
        `;
        chartHistory = [];
        currentSessionId = Date.now().toString();
        dashboardInput.value = '';
    }
}

// Export chart block to PDF
async function exportChartToPDF(btn) {
    const block = btn.closest('.chart-block');
    if (!block) return;

    btn.textContent = 'Generating...';
    btn.disabled = true;

    let printStyle = document.getElementById('pdf-print-styles');
    if (!printStyle) {
        printStyle = document.createElement('style');
        printStyle.id = 'pdf-print-styles';
        printStyle.textContent = `
            .pdf-export-mode {
                background: #ffffff !important;
                box-shadow: none !important;
                border: none !important;
            }
            .pdf-export-mode .chart-header {
                background: #ffffff !important;
                color: #1d1d1f !important;
                border-bottom: 2px solid #1d1d1f !important;
            }
            .pdf-export-mode .chart-question { color: #1d1d1f !important; }
            .pdf-export-mode .chart-meta { color: #6e6e73 !important; }
            .pdf-export-mode .chart-actions { display: none !important; }
        `;
        document.head.appendChild(printStyle);
    }

    block.classList.add('pdf-export-mode');
    await new Promise(r => setTimeout(r, 150));

    const ts = new Date().toISOString().slice(0, 10);
    try {
        await html2pdf().set({
            margin: [10, 10, 10, 10],
            filename: `Data-Dashboard-${ts}.pdf`,
            image: { type: 'jpeg', quality: 0.95 },
            html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff' },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'landscape' }
        }).from(block).save();
    } catch (e) {
        alert('Export failed: ' + e.message);
    } finally {
        block.classList.remove('pdf-export-mode');
        btn.textContent = 'Export PDF';
        btn.disabled = false;
    }
}

// --- Session History ---
function toggleSessionsPanel() {
    const panel = document.getElementById('sessions-panel');
    const overlay = document.getElementById('sessions-overlay');
    if (panel.style.display === 'none') {
        renderSessionsList();
        panel.style.display = 'flex';
        overlay.style.display = 'block';
    } else {
        panel.style.display = 'none';
        overlay.style.display = 'none';
    }
}

function saveCurrentSession() {
    if (chartHistory.length === 0) return;

    const entries = chartHistory.map(h => ({
        question: h.question,
        chartType: h.result.chart_type,
        rowCount: h.result.row_count,
        timestamp: h.timestamp
    }));

    const existingIdx = savedSessions.findIndex(s => s.id === currentSessionId);
    const session = {
        id: currentSessionId,
        title: chartHistory[0].question.substring(0, 80),
        timestamp: Date.now(),
        entries: entries
    };

    if (existingIdx >= 0) {
        savedSessions[existingIdx] = session;
    } else {
        savedSessions.unshift(session);
        if (savedSessions.length > MAX_SESSIONS) savedSessions.pop();
    }

    localStorage.setItem('dashboard_sessions', JSON.stringify(savedSessions));
    updateSessionsBadge();
}

function updateSessionsBadge() {
    const badge = document.getElementById('sessions-count');
    if (badge) badge.textContent = savedSessions.length;
}

function renderSessionsList() {
    const list = document.getElementById('sessions-list');
    if (!list) return;

    if (savedSessions.length === 0) {
        list.innerHTML = '<p style="color: #666; text-align: center; padding: 40px 20px;">No saved sessions</p>';
        return;
    }

    list.innerHTML = savedSessions.map((session, i) => `
        <div class="session-entry" onclick="loadSession(${i})">
            <button class="session-delete" onclick="event.stopPropagation(); deleteSession(${i})">&times;</button>
            <div class="session-title">${escapeHtml(session.title)}</div>
            <div class="session-meta">
                ${session.entries.length} charts | ${new Date(session.timestamp).toLocaleString()}
            </div>
        </div>
    `).join('');
}

function loadSession(index) {
    const session = savedSessions[index];
    if (!session) return;

    const blocks = conversation.querySelectorAll('.chart-block, .welcome-message');
    blocks.forEach(b => b.remove());

    session.entries.forEach(entry => {
        const html = `
            <div class="chart-block">
                <div class="chart-header">
                    <div class="chart-question">${escapeHtml(entry.question)}</div>
                    <div class="chart-meta">${entry.rowCount} rows | ${entry.chartType} chart | ${new Date(entry.timestamp).toLocaleString()}</div>
                </div>
                <div class="chart-body" style="padding: 24px;">
                    <p style="color: #86868b; font-style: italic;">Charts are not available for past sessions. Re-ask the question to regenerate.</p>
                </div>
            </div>
        `;
        conversation.insertAdjacentHTML('beforeend', html);
    });

    toggleSessionsPanel();
    conversation.scrollTop = 0;
}

function deleteSession(index) {
    savedSessions.splice(index, 1);
    localStorage.setItem('dashboard_sessions', JSON.stringify(savedSessions));
    updateSessionsBadge();
    renderSessionsList();
}

// --- Language Toggle ---
function toggleLanguage() {
    currentLanguage = currentLanguage === 'en' ? 'zh' : 'en';
    languageLabel.textContent = currentLanguage === 'en' ? 'EN' : 'CN';

    if (currentLanguage === 'zh') {
        dashboardInput.placeholder = '提出任何关于数据的问题... 例如："按品牌显示月度收入趋势"';
    } else {
        dashboardInput.placeholder = 'Ask any question about your data... e.g., "Show me monthly revenue trends by brand"';
    }
}

// Utility: Escape HTML
function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}
