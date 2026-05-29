// GBIS Business Analysis - Dashboard Interface

// Detect base path for reverse proxy support
const BASE_PATH = document.querySelector('script[src*="main.js"]')?.src.replace(/\/static\/js\/main\.js.*/, '') || '';

function apiUrl(path) {
    return BASE_PATH + path;
}

// Global variables
let currentData = [];
let currentColumns = [];
let currentQuery = '';
let currentQuestion = '';
let aiEnabled = false;

// Query History
const MAX_HISTORY = 5;
let queryHistory = JSON.parse(sessionStorage.getItem('query_history') || '[]');

// DOM Elements
const queryInput = document.getElementById('query-input');
const executeBtn = document.getElementById('execute-btn');
const clearBtn = document.getElementById('clear-btn');
const testConnectionBtn = document.getElementById('test-connection-btn');
const connectionStatus = document.getElementById('connection-status');
const queryStatus = document.getElementById('query-status');
const resultsContainer = document.getElementById('results-container');
const resultsInfo = document.getElementById('results-info');
const savedQueriesSelect = document.getElementById('saved-queries');
const chartControls = document.getElementById('chart-controls');
const chartType = document.getElementById('chart-type');
const xColumn = document.getElementById('x-column');
const yColumn = document.getElementById('y-column');
const generateChartBtn = document.getElementById('generate-chart-btn');
const chartContainer = document.getElementById('chart-container');

// AI Elements
const nlInput = document.getElementById('nl-input');
const generateQueryBtn = document.getElementById('generate-query-btn');
const aiStatusMessage = document.getElementById('ai-status-message');
const aiStatusIndicator = document.getElementById('ai-status-indicator');
const aiStatusText = document.getElementById('ai-status-text');
const analyzeBtn = document.getElementById('analyze-btn');
const analysisSection = document.getElementById('analysis-section');
const analysisContainer = document.getElementById('analysis-container');

// Event Listeners
testConnectionBtn.addEventListener('click', testConnection);
executeBtn.addEventListener('click', executeQuery);
clearBtn.addEventListener('click', clearQuery);
savedQueriesSelect.addEventListener('change', loadSavedQuery);
generateChartBtn.addEventListener('click', generateChart);
generateQueryBtn.addEventListener('click', generateQueryFromNL);
analyzeBtn.addEventListener('click', analyzeData);

nlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') generateQueryFromNL();
});

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadSavedQueries();
    checkAIStatus();
    updateHistoryBadge();
});

// --- Query History ---
function toggleHistoryPanel() {
    const panel = document.getElementById('history-panel');
    const overlay = document.getElementById('history-overlay');
    if (panel.style.display === 'none') {
        renderHistoryList();
        panel.style.display = 'flex';
        overlay.style.display = 'block';
    } else {
        panel.style.display = 'none';
        overlay.style.display = 'none';
    }
}

function addToHistory(question, sql, result) {
    queryHistory.unshift({
        question: question || 'Manual query',
        sql: sql,
        data: result.data ? result.data.slice(0, 20) : [],
        columns: result.columns || [],
        rowCount: result.row_count || 0,
        executionTime: result.execution_time || 0,
        timestamp: new Date().toISOString()
    });
    if (queryHistory.length > MAX_HISTORY) queryHistory.pop();
    sessionStorage.setItem('query_history', JSON.stringify(queryHistory));
    updateHistoryBadge();
}

function updateHistoryBadge() {
    const badge = document.getElementById('history-count');
    if (badge) badge.textContent = queryHistory.length;
}

function renderHistoryList() {
    const list = document.getElementById('history-list');
    if (!list) return;

    if (queryHistory.length === 0) {
        list.innerHTML = '<p style="color: #666; text-align: center; padding: 40px 20px;">No query history yet</p>';
        return;
    }

    list.innerHTML = queryHistory.map((entry, i) => `
        <div class="history-entry" onclick="loadHistoryEntry(${i})">
            <div class="history-entry-question">${escapeHtml(entry.question)}</div>
            <div class="history-entry-sql">${escapeHtml(entry.sql)}</div>
            <div class="history-entry-meta">${entry.rowCount} rows | ${new Date(entry.timestamp).toLocaleString()}</div>
        </div>
    `).join('');
}

function loadHistoryEntry(index) {
    const entry = queryHistory[index];
    if (!entry) return;

    queryInput.value = entry.sql;
    if (entry.question !== 'Manual query') {
        nlInput.value = entry.question;
    }

    if (entry.data && entry.data.length > 0) {
        displayResults({
            data: entry.data,
            columns: entry.columns,
            row_count: entry.rowCount,
            execution_time: entry.executionTime,
            success: true
        });
        populateColumnSelectors(entry.columns);
        currentData = entry.data;
        currentColumns = entry.columns;
        currentQuery = entry.sql;
    }

    toggleHistoryPanel();
}

// --- Core Functions ---

async function testConnection() {
    showStatus('Testing connection...', 'info');
    try {
        const response = await fetch(apiUrl('/api/test-connection'));
        const data = await response.json();

        if (data.success) {
            connectionStatus.textContent = 'Connected';
            connectionStatus.className = 'connected';
            showStatus(data.message, 'success');
        } else {
            connectionStatus.textContent = 'Disconnected';
            connectionStatus.className = 'disconnected';
            showStatus(`Connection failed: ${data.error}`, 'error');
        }
    } catch (error) {
        connectionStatus.textContent = 'Disconnected';
        connectionStatus.className = 'disconnected';
        showStatus(`Error: ${error.message}`, 'error');
    }
}

async function executeQuery() {
    const query = queryInput.value.trim();
    if (!query) { showStatus('Please enter a query', 'error'); return; }

    executeBtn.disabled = true;
    executeBtn.textContent = 'Executing...';
    resultsContainer.innerHTML = '<div class="loading">Executing query</div>';
    showStatus('Executing query...', 'info');

    try {
        const response = await fetch(apiUrl('/api/execute-query'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        const data = await response.json();

        if (data.success) {
            currentData = data.data;
            currentColumns = data.columns;
            currentQuery = query;
            displayResults(data);
            populateColumnSelectors(data.columns);
            showStatus(
                `Query executed in ${data.execution_time.toFixed(3)}s - ${data.row_count} rows returned`,
                'success'
            );

            // Add to history
            addToHistory(currentQuestion || '', query, data);
            currentQuestion = '';

            if (aiEnabled && data.row_count > 0) {
                analyzeBtn.style.display = 'inline-block';
            }
        } else {
            resultsContainer.innerHTML = '<p class="placeholder">Query failed. See error above.</p>';
            showStatus(`Error: ${data.error}`, 'error');
            analyzeBtn.style.display = 'none';
        }
    } catch (error) {
        resultsContainer.innerHTML = '<p class="placeholder">Request failed. See error above.</p>';
        showStatus(`Error: ${error.message}`, 'error');
    } finally {
        executeBtn.disabled = false;
        executeBtn.textContent = 'Execute Query';
    }
}

function displayResults(data) {
    if (!data.data || data.data.length === 0) {
        resultsContainer.innerHTML = '<p class="placeholder">No results found</p>';
        resultsInfo.textContent = '';
        return;
    }

    resultsInfo.textContent = `${data.row_count} rows | ${data.columns.length} columns | ${data.execution_time.toFixed(3)}s`;

    let tableHTML = '<div class="table-wrapper"><table class="results-table"><thead><tr>';
    data.columns.forEach(col => { tableHTML += `<th>${escapeHtml(col)}</th>`; });
    tableHTML += '</tr></thead><tbody>';

    data.data.forEach(row => {
        tableHTML += '<tr>';
        data.columns.forEach(col => {
            const value = row[col] !== null && row[col] !== undefined ? row[col] : '';
            tableHTML += `<td>${escapeHtml(String(value))}</td>`;
        });
        tableHTML += '</tr>';
    });

    tableHTML += '</tbody></table></div>';
    resultsContainer.innerHTML = tableHTML;
}

function populateColumnSelectors(columns) {
    if (!columns || columns.length === 0) { chartControls.style.display = 'none'; return; }
    chartControls.style.display = 'flex';
    xColumn.innerHTML = '<option value="">Select X Column</option>';
    yColumn.innerHTML = '<option value="">Select Y Column</option>';
    columns.forEach(col => {
        xColumn.innerHTML += `<option value="${col}">${col}</option>`;
        yColumn.innerHTML += `<option value="${col}">${col}</option>`;
    });
}

// Dark Plotly layout
const darkLayout = {
    paper_bgcolor: '#ffffff',
    plot_bgcolor: '#ffffff',
    font: { color: '#1d1d1f', size: 13 },
    xaxis: { gridcolor: '#e8e8ed', zerolinecolor: '#d2d2d7' },
    yaxis: { gridcolor: '#e8e8ed', zerolinecolor: '#d2d2d7' },
    legend: { font: { color: '#424245' } }
};

async function generateChart() {
    const selectedChartType = chartType.value;
    const selectedX = xColumn.value;
    const selectedY = yColumn.value;

    if (!selectedX || !selectedY) { alert('Please select both X and Y columns'); return; }
    if (!currentData || currentData.length === 0) { alert('No data available. Execute a query first.'); return; }

    chartContainer.innerHTML = '<div class="loading">Generating chart</div>';

    try {
        const response = await fetch(apiUrl('/api/generate-chart'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data: currentData,
                chart_type: selectedChartType,
                x_column: selectedX,
                y_column: selectedY
            })
        });

        const data = await response.json();

        if (data.success) {
            const mergedLayout = Object.assign({}, data.chart.layout || {}, darkLayout);
            Plotly.newPlot('chart-container', data.chart.data, mergedLayout, { responsive: true });
        } else {
            chartContainer.innerHTML = `<p class="placeholder">Chart generation failed: ${data.error}</p>`;
        }
    } catch (error) {
        chartContainer.innerHTML = `<p class="placeholder">Error: ${error.message}</p>`;
    }
}

async function loadSavedQueries() {
    try {
        const response = await fetch(apiUrl('/api/saved-queries'));
        const data = await response.json();
        data.queries.forEach(query => {
            const option = document.createElement('option');
            option.value = query.query;
            option.textContent = `${query.name} - ${query.description}`;
            savedQueriesSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load saved queries:', error);
    }
}

function loadSavedQuery() {
    const query = savedQueriesSelect.value;
    if (query) queryInput.value = query;
}

function clearQuery() {
    queryInput.value = '';
    nlInput.value = '';
    resultsContainer.innerHTML = '<p class="placeholder">Execute a query to see results</p>';
    resultsInfo.textContent = '';
    chartContainer.innerHTML = '<p class="placeholder">Select columns and generate a chart from your query results</p>';
    chartControls.style.display = 'none';
    queryStatus.style.display = 'none';
    aiStatusMessage.style.display = 'none';
    analyzeBtn.style.display = 'none';
    analysisSection.style.display = 'none';
    currentData = [];
    currentColumns = [];
    currentQuery = '';
    currentQuestion = '';
}

function showStatus(message, type) {
    queryStatus.textContent = message;
    queryStatus.className = `status-message ${type}`;
}

function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

// --- AI Functions ---

async function checkAIStatus() {
    try {
        const response = await fetch(apiUrl('/api/ai/status'));
        const data = await response.json();
        aiEnabled = data.enabled;
        const statusDot = aiStatusIndicator.querySelector('.status-dot');
        if (data.enabled) {
            statusDot.className = 'status-dot active';
            aiStatusText.textContent = 'AI Ready';
            generateQueryBtn.disabled = false;
        } else {
            statusDot.className = 'status-dot inactive';
            aiStatusText.textContent = 'AI Unavailable';
            generateQueryBtn.disabled = true;
        }
    } catch (error) {
        console.error('Failed to check AI status:', error);
        const statusDot = aiStatusIndicator.querySelector('.status-dot');
        statusDot.className = 'status-dot inactive';
        aiStatusText.textContent = 'AI Error';
    }
}

async function generateQueryFromNL() {
    const question = nlInput.value.trim();
    if (!question) { showAIStatus('Please enter a question', 'error'); return; }
    if (!aiEnabled) { showAIStatus('AI is not available', 'error'); return; }

    generateQueryBtn.disabled = true;
    generateQueryBtn.textContent = 'Generating...';
    showAIStatus('AI is generating your SQL query...', 'info');

    try {
        const response = await fetch(apiUrl('/api/ai/generate-query'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });

        const data = await response.json();

        if (data.success) {
            queryInput.value = data.sql;
            currentQuestion = question;
            showAIStatus(`Query generated: ${data.explanation}`, 'success');

            if (confirm('Query generated. Execute it now?')) {
                executeQuery();
            }

            if (data.suggested_chart) chartType.value = data.suggested_chart;
        } else {
            showAIStatus(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showAIStatus(`Error: ${error.message}`, 'error');
    } finally {
        generateQueryBtn.disabled = false;
        generateQueryBtn.textContent = 'Generate Query';
    }
}

async function analyzeData() {
    if (!aiEnabled) { alert('AI analysis is not available'); return; }
    if (!currentData || currentData.length === 0) { alert('No data to analyze. Execute a query first.'); return; }

    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing...';
    analysisContainer.innerHTML = '<div class="loading">AI is analyzing your data</div>';
    analysisSection.style.display = 'block';

    try {
        const response = await fetch(apiUrl('/api/ai/analyze-data'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: currentQuery,
                data: currentData,
                question: currentQuestion
            })
        });

        const data = await response.json();

        if (data.success) {
            const formattedAnalysis = data.analysis
                .replace(/\n/g, '<br>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/^- (.+)$/gm, '<li>$1</li>')
                .replace(/(<li>.*<\/li>)/s, '<ul>$&</ul>');
            analysisContainer.innerHTML = formattedAnalysis;
        } else {
            analysisContainer.innerHTML = `<p class="placeholder">Analysis failed: ${data.error}</p>`;
        }
    } catch (error) {
        analysisContainer.innerHTML = `<p class="placeholder">Error: ${error.message}</p>`;
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'AI Analysis';
    }
}

function showAIStatus(message, type) {
    aiStatusMessage.textContent = message;
    aiStatusMessage.className = `status-message ${type}`;
}
