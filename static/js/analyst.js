// GBIS Deep Insight - Analyst Interface

// Detect base path for reverse proxy support
const BASE_PATH = document.querySelector('script[src*="analyst.js"]')?.src.replace(/\/static\/js\/analyst\.js.*/, '') || '';

function apiUrl(path) {
    return BASE_PATH + path;
}

// DOM Elements
const conversation = document.getElementById('conversation');
const analystInput = document.getElementById('analyst-input');
const analyzeBtn = document.getElementById('analyze-btn');
const clearBtn = document.getElementById('clear-btn');
const sessionsBtn = document.getElementById('sessions-btn');
const languageToggle = document.getElementById('language-toggle');
const languageLabel = document.getElementById('language-label');
const btnText = analyzeBtn.querySelector('.btn-text');
const btnLoading = analyzeBtn.querySelector('.btn-loading');

// State
let analysisHistory = [];
let currentLanguage = 'en';

// Session History
const MAX_SESSIONS = 5;
let savedSessions = JSON.parse(localStorage.getItem('analyst_sessions') || '[]');
let currentSessionId = Date.now().toString();

// Event Listeners
if (analyzeBtn) {
    analyzeBtn.addEventListener('click', performAnalysis);
}
clearBtn.addEventListener('click', clearConversation);
languageToggle.addEventListener('click', toggleLanguage);
sessionsBtn.addEventListener('click', toggleSessionsPanel);

analystInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        performAnalysis();
    }
});

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('example-btn')) {
        const question = e.target.getAttribute('data-question');
        analystInput.value = question;
        performAnalysis();
    }
});

// Initialize
updateSessionsBadge();

// Main Analysis Function
async function performAnalysis() {
    const question = analystInput.value.trim();
    if (!question) { alert('Please enter a question'); return; }

    analyzeBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'inline';
    analystInput.disabled = true;

    const welcomeMsg = document.querySelector('.welcome-message');
    if (welcomeMsg) welcomeMsg.remove();

    const loadingDiv = showLoading(question);

    try {
        const response = await fetch(apiUrl('/api/ai/comprehensive-analysis'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, language: currentLanguage })
        });

        const result = await response.json();
        loadingDiv.remove();

        if (result.success) {
            displayAnalysis(result);
            analysisHistory.push(result);
            saveCurrentSession();
            analystInput.value = '';
        } else {
            showError(result.error || 'Analysis failed');
        }
    } catch (error) {
        loadingDiv.remove();
        showError('Network error: ' + error.message);
    } finally {
        analyzeBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        analystInput.disabled = false;
        analystInput.focus();
    }
}

// Show Loading State
function showLoading(question) {
    const loadingHTML = `
        <div class="analysis-block loading-analysis">
            <div class="loading-spinner"></div>
            <p><strong>Analyzing:</strong> ${escapeHtml(question)}</p>
            <p style="margin-top: 10px; font-size: 13px; color: #666;">
                Creating analysis plan > Executing queries > Generating visualizations > Producing insights...
            </p>
        </div>
    `;
    conversation.insertAdjacentHTML('beforeend', loadingHTML);
    conversation.scrollTop = conversation.scrollHeight;
    return conversation.lastElementChild;
}

// Display Complete Analysis
function displayAnalysis(result) {
    const timestamp = new Date(result.timestamp).toLocaleString();

    let html = `
        <div class="analysis-block">
            <div class="analysis-header">
                <div class="analysis-question">${escapeHtml(result.question)}</div>
                <div class="analysis-metadata">
                    ${result.results.length} queries executed |
                    ${result.visualizations.length} visualizations |
                    ${timestamp}
                </div>
            </div>

            <div class="analysis-approach">
                <h3>Analysis Approach</h3>
                <p>${escapeHtml(result.analysis_approach)}</p>
            </div>

            <div class="analysis-content">
    `;

    if (result.insights && result.insights.success) {
        html += `
            <div class="executive-summary">
                <h3>Insights & Findings</h3>
                <div class="executive-summary-content">
                    ${marked.parse(result.insights.content)}
                </div>
            </div>
        `;
    }

    html += '<h3>Data Analysis</h3>';
    result.results.forEach((queryResult, index) => {
        html += renderQueryResult(queryResult, index + 1);
    });

    const chartTimestamp = Date.now();

    if (result.visualizations && result.visualizations.length > 0) {
        html += `<div class="visualizations-section"><h3>Visualizations</h3>`;
        result.visualizations.forEach((viz, index) => {
            html += `<div class="chart-container" id="chart-${chartTimestamp}-${index}"></div>`;
        });
        html += '</div>';
    }

    // Export button at bottom-right
    html += `
            <div class="export-block-container">
                <button class="btn-export" onclick="exportBlockToPDF(this)">Export PDF</button>
            </div>
            </div>
        </div>
    `;

    conversation.insertAdjacentHTML('beforeend', html);

    if (result.visualizations && result.visualizations.length > 0) {
        result.visualizations.forEach((viz, index) => {
            const chartId = `chart-${chartTimestamp}-${index}`;
            setTimeout(() => renderVisualization(chartId, viz), 100);
        });
    }

    conversation.scrollTop = conversation.scrollHeight;
}

// Render Individual Query Result
function renderQueryResult(result, stepNumber) {
    if (!result.success) {
        return `
            <div class="query-result">
                <div class="query-header">
                    <div class="query-title">Error - Step ${stepNumber}: ${escapeHtml(result.title)}</div>
                </div>
                <div class="query-data" style="color: #f87171; padding: 20px;">
                    ${escapeHtml(result.error || 'Query failed')}
                </div>
            </div>
        `;
    }

    let html = `
        <div class="query-result">
            <div class="query-header">
                <div class="query-title">Step ${stepNumber}: ${escapeHtml(result.title)}</div>
                <div class="query-meta">
                    ${result.row_count} rows | ${result.execution_time.toFixed(3)}s
                </div>
            </div>
            <div class="query-sql">${escapeHtml(result.sql)}</div>
    `;

    if (result.data && result.data.length > 0) {
        html += '<div class="query-data"><div class="query-table-container">';
        html += '<table class="query-table"><thead><tr>';
        result.columns.forEach(col => { html += `<th>${escapeHtml(col)}</th>`; });
        html += '</tr></thead><tbody>';

        const displayRows = result.data.slice(0, 10);
        displayRows.forEach(row => {
            html += '<tr>';
            result.columns.forEach(col => {
                const value = row[col] !== null && row[col] !== undefined ? row[col] : '';
                html += `<td>${escapeHtml(String(value))}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table></div>';
        if (result.data.length > 10) {
            html += `<p style="text-align: center; color: #666; margin-top: 10px; font-size: 12px;">Showing 10 of ${result.row_count} rows</p>`;
        }
        html += '</div>';
    }

    html += '</div>';
    return html;
}

// Render Visualization with dark theme
function renderVisualization(containerId, viz) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const darkLayout = {
        paper_bgcolor: '#ffffff',
        plot_bgcolor: '#ffffff',
        font: { color: '#1d1d1f', size: 13 },
        xaxis: { gridcolor: '#e8e8ed', zerolinecolor: '#d2d2d7' },
        yaxis: { gridcolor: '#e8e8ed', zerolinecolor: '#d2d2d7' },
        legend: { font: { color: '#424245' } }
    };

    if (viz.type === 'table') {
        container.innerHTML = `
            <div class="chart-title">${escapeHtml(viz.title)}</div>
            ${renderTable(viz.data)}
        `;
    } else {
        container.innerHTML = `<div class="chart-title">${escapeHtml(viz.title)}</div>`;
        const chartDiv = document.createElement('div');
        chartDiv.style.height = '400px';
        container.appendChild(chartDiv);

        try {
            const mergedLayout = Object.assign({}, viz.chart.layout || {}, darkLayout);
            Plotly.newPlot(chartDiv, viz.chart.data, mergedLayout, {
                responsive: true,
                displayModeBar: true,
                displaylogo: false
            });
        } catch (e) {
            console.error('Chart rendering failed:', e);
        }
    }
}

// Render Table
function renderTable(data) {
    if (!data || data.length === 0) return '<p style="color: #666;">No data</p>';
    const columns = Object.keys(data[0]);

    let html = '<div class="query-table-container"><table class="query-table"><thead><tr>';
    columns.forEach(col => { html += `<th>${escapeHtml(col)}</th>`; });
    html += '</tr></thead><tbody>';

    data.forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
            const value = row[col] !== null && row[col] !== undefined ? row[col] : '';
            html += `<td>${escapeHtml(String(value))}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table></div>';
    return html;
}

// Show Error
function showError(message) {
    const errorHTML = `
        <div class="analysis-block" style="border-left: 3px solid #f87171;">
            <div class="analysis-content">
                <h3 style="color: #f87171;">Error</h3>
                <p style="color: #a0a0a0; margin-top: 10px;">${escapeHtml(message)}</p>
            </div>
        </div>
    `;
    conversation.insertAdjacentHTML('beforeend', errorHTML);
    conversation.scrollTop = conversation.scrollHeight;
}

// Clear Conversation
function clearConversation() {
    if (confirm('Clear all analysis history?')) {
        if (analysisHistory.length > 0) saveCurrentSession();
        conversation.innerHTML = `
            <div class="welcome-message">
                <h2>Ready for a new deep analysis</h2>
                <p>Ask me any complex question about your data</p>
            </div>
        `;
        analysisHistory = [];
        currentSessionId = Date.now().toString();
        analystInput.value = '';
    }
}

// Export single analysis block to PDF using html2pdf.js
async function exportBlockToPDF(btn) {
    const block = btn.closest('.analysis-block');
    if (!block) return;

    btn.textContent = 'Generating...';
    btn.disabled = true;

    // Apply print-friendly styles
    block.classList.add('pdf-export-mode');

    // Inject print styles if not already present
    let printStyle = document.getElementById('pdf-print-styles');
    if (!printStyle) {
        printStyle = document.createElement('style');
        printStyle.id = 'pdf-print-styles';
        printStyle.textContent = `
            .pdf-export-mode {
                background: #ffffff !important;
                box-shadow: none !important;
                border: none !important;
                border-radius: 0 !important;
            }
            .pdf-export-mode .analysis-header {
                background: #ffffff !important;
                color: #1d1d1f !important;
                border-bottom: 2px solid #1d1d1f !important;
            }
            .pdf-export-mode .analysis-question { color: #1d1d1f !important; }
            .pdf-export-mode .analysis-metadata { color: #6e6e73 !important; }
            .pdf-export-mode .analysis-approach {
                background: #fafafa !important;
                border-bottom: 1px solid #e0e0e0 !important;
            }
            .pdf-export-mode .analysis-approach h3,
            .pdf-export-mode .analysis-approach p { color: #333 !important; }
            .pdf-export-mode .executive-summary {
                background: #f9f9f9 !important;
                border-left: 4px solid #1d1d1f !important;
            }
            .pdf-export-mode .executive-summary h3 { color: #1d1d1f !important; }
            .pdf-export-mode .executive-summary-content,
            .pdf-export-mode .executive-summary-content li,
            .pdf-export-mode .executive-summary-content td,
            .pdf-export-mode .executive-summary-content p { color: #333 !important; }
            .pdf-export-mode .executive-summary-content strong { color: #1d1d1f !important; }
            .pdf-export-mode .executive-summary-content th {
                background: #f0f0f0 !important; color: #1d1d1f !important;
            }
            .pdf-export-mode .query-header { background: #f5f5f5 !important; }
            .pdf-export-mode .query-title { color: #1d1d1f !important; }
            .pdf-export-mode .query-sql {
                background: #f5f5f5 !important; color: #333 !important;
                border: 1px solid #e0e0e0 !important;
            }
            .pdf-export-mode .query-data { background: #fff !important; }
            .pdf-export-mode .query-table th { background: #f0f0f0 !important; color: #1d1d1f !important; }
            .pdf-export-mode .query-table td { color: #333 !important; }
            .pdf-export-mode .analysis-content h3 { color: #1d1d1f !important; }
            .pdf-export-mode .chart-container { background: #fff !important; }
            .pdf-export-mode .chart-title { color: #1d1d1f !important; }
            .pdf-export-mode .export-block-container { display: none !important; }

            /* Page break hints for html2pdf */
            .pdf-export-mode .query-result { page-break-inside: avoid; }
            .pdf-export-mode .executive-summary { page-break-inside: avoid; }
            .pdf-export-mode .chart-container { page-break-inside: avoid; }
            .pdf-export-mode .analysis-header { page-break-after: avoid; }
            .pdf-export-mode .analysis-approach { page-break-after: avoid; }
            .pdf-export-mode h3 { page-break-after: avoid; }
            .pdf-export-mode tr { page-break-inside: avoid; }
        `;
        document.head.appendChild(printStyle);
    }

    await new Promise(r => setTimeout(r, 150));

    const ts = new Date().toISOString().slice(0, 10);
    const opt = {
        margin: [12, 10, 12, 10],  // top, right, bottom, left (mm)
        filename: `GBIS-Deep-Insight-${ts}.pdf`,
        image: { type: 'jpeg', quality: 0.95 },
        html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: '#ffffff',
            logging: false
        },
        jsPDF: {
            unit: 'mm',
            format: 'a4',
            orientation: 'portrait'
        },
        pagebreak: {
            mode: ['avoid-all', 'css', 'legacy'],
            before: [],
            after: [],
            avoid: ['.query-result', '.executive-summary', '.chart-container', '.analysis-header', 'tr', 'h3']
        }
    };

    try {
        await html2pdf().set(opt).from(block).save();
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
    if (analysisHistory.length === 0) return;

    const conversations = analysisHistory.map(r => ({
        question: r.question,
        analysisApproach: r.analysis_approach,
        insightsContent: r.insights && r.insights.success ? r.insights.content : '',
        queryCount: r.results ? r.results.length : 0,
        vizCount: r.visualizations ? r.visualizations.length : 0,
        timestamp: r.timestamp
    }));

    // Check if current session already exists
    const existingIdx = savedSessions.findIndex(s => s.id === currentSessionId);
    const session = {
        id: currentSessionId,
        title: analysisHistory[0].question.substring(0, 80),
        timestamp: Date.now(),
        conversations: conversations
    };

    if (existingIdx >= 0) {
        savedSessions[existingIdx] = session;
    } else {
        savedSessions.unshift(session);
        if (savedSessions.length > MAX_SESSIONS) savedSessions.pop();
    }

    localStorage.setItem('analyst_sessions', JSON.stringify(savedSessions));
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
        list.innerHTML = '<p style="color: #666; text-align: center; padding: 40px 20px;">No saved conversations</p>';
        return;
    }

    list.innerHTML = savedSessions.map((session, i) => `
        <div class="session-entry" onclick="loadSession(${i})">
            <button class="session-delete" onclick="event.stopPropagation(); deleteSession(${i})">&times;</button>
            <div class="session-title">${escapeHtml(session.title)}</div>
            <div class="session-meta">
                ${session.conversations.length} analysis | ${new Date(session.timestamp).toLocaleString()}
            </div>
        </div>
    `).join('');
}

function loadSession(index) {
    const session = savedSessions[index];
    if (!session) return;

    // Clear current view
    const blocks = conversation.querySelectorAll('.analysis-block, .welcome-message');
    blocks.forEach(b => b.remove());

    // Display each conversation entry as read-only
    session.conversations.forEach(conv => {
        let html = `
            <div class="analysis-block">
                <div class="analysis-header">
                    <div class="analysis-question">${escapeHtml(conv.question)}</div>
                    <div class="analysis-metadata">
                        ${conv.queryCount} queries | ${conv.vizCount} visualizations | ${new Date(conv.timestamp).toLocaleString()}
                    </div>
                </div>
                <div class="analysis-approach">
                    <h3>Analysis Approach</h3>
                    <p>${escapeHtml(conv.analysisApproach)}</p>
                </div>
                <div class="analysis-content">
        `;

        if (conv.insightsContent) {
            html += `
                <div class="executive-summary">
                    <h3>Insights & Findings</h3>
                    <div class="executive-summary-content">
                        ${marked.parse(conv.insightsContent)}
                    </div>
                </div>
            `;
        }

        html += `
                <p style="color: #666; font-style: italic; font-size: 13px;">Charts and raw data are not available for past sessions.</p>
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
    localStorage.setItem('analyst_sessions', JSON.stringify(savedSessions));
    updateSessionsBadge();
    renderSessionsList();
}

// --- Language Toggle ---
function toggleLanguage() {
    currentLanguage = currentLanguage === 'en' ? 'zh' : 'en';
    languageLabel.textContent = currentLanguage === 'en' ? 'EN' : 'CN';

    if (currentLanguage === 'zh') {
        analystInput.placeholder = '提出任何复杂的问题... 例如："分析STAR品牌的收入构成和趋势"';
    } else {
        analystInput.placeholder = 'Ask any complex question... e.g., "Analyze STAR brand revenue components and trends"';
    }

    translateAllResults();
}

async function translateAllResults() {
    const analysisBlocks = document.querySelectorAll('.analysis-block:not(.loading-analysis)');
    if (analysisBlocks.length === 0 || analysisHistory.length === 0) return;

    const statusDiv = document.createElement('div');
    statusDiv.className = 'translation-status';
    statusDiv.innerHTML = `
        <div style="background: #1a1a1a; border: 1px solid #2a2a2a; padding: 10px; border-radius: 4px; margin: 10px; text-align: center; color: #a0a0a0;">
            ${currentLanguage === 'zh' ? 'Translating to Chinese...' : 'Translating to English...'}
        </div>
    `;
    conversation.insertBefore(statusDiv, conversation.firstChild);

    for (let i = 0; i < analysisHistory.length; i++) {
        const result = analysisHistory[i];
        if (!result.insights || !result.insights.content) continue;
        try {
            const response = await fetch(apiUrl('/api/ai/translate-insights'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    insights: result.insights.content,
                    analysis_approach: result.analysis_approach,
                    target_language: currentLanguage
                })
            });
            const translation = await response.json();
            if (translation.success) {
                analysisHistory[i].insights.content = translation.insights;
                analysisHistory[i].analysis_approach = translation.analysis_approach;
            }
        } catch (error) {
            console.error('Translation error:', error);
        }
    }

    statusDiv.remove();
    redisplayAllResults();
}

function redisplayAllResults() {
    const blocks = conversation.querySelectorAll('.analysis-block:not(.welcome-message)');
    blocks.forEach(block => block.remove());
    analysisHistory.forEach(result => { displayAnalysis(result); });
}

// Utility: Escape HTML
function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}
