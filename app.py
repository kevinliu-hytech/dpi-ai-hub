from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import mysql.connector
from mysql.connector import Error
from databricks import sql as databricks_sql
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
from datetime import datetime
from config import Config
from ai_query_generator_bedrock import AIQueryGenerator
from ai_analyst_agent import AIAnalystAgent

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
CORS(app)

# --- Access Control ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Load user whitelist from .env
# --- User Management ---
import hashlib

USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.json')

WHITELIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'whitelist.json')

def load_allowed_emails():
    """Load whitelist: from whitelist.json first, fallback to .env"""
    if os.path.exists(WHITELIST_FILE):
        with open(WHITELIST_FILE, 'r') as f:
            data = json.load(f)
            return [e.lower() for e in data.get('allowed_emails', [])]
    emails_str = os.getenv('ALLOWED_EMAILS', '')
    if not emails_str:
        return []
    emails = [e.strip().lower() for e in emails_str.split(',') if e.strip()]
    # Migrate to whitelist.json
    save_whitelist(emails)
    return emails

def load_admin_emails():
    """Load admin emails from whitelist.json or .env"""
    if os.path.exists(WHITELIST_FILE):
        with open(WHITELIST_FILE, 'r') as f:
            data = json.load(f)
            return [e.lower() for e in data.get('admin_emails', [])]
    emails_str = os.getenv('ADMIN_EMAILS', '')
    if not emails_str:
        return []
    return [e.strip().lower() for e in emails_str.split(',') if e.strip()]

def save_whitelist(allowed_emails, admin_emails=None):
    """Save whitelist to JSON file"""
    if admin_emails is None:
        admin_emails = load_admin_emails()
    with open(WHITELIST_FILE, 'w') as f:
        json.dump({
            'allowed_emails': allowed_emails,
            'admin_emails': admin_emails
        }, f, indent=2)

def load_registered_users():
    """Load registered users from JSON file"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_registered_users(users):
    """Save registered users to JSON file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

ALLOWED_EMAILS = load_allowed_emails()
ADMIN_EMAILS = load_admin_emails()
print(f"✓ Access control: {len(ALLOWED_EMAILS)} emails whitelisted, {len(ADMIN_EMAILS)} admins")

class User(UserMixin):
    def __init__(self, email, name='', role='analyst'):
        self.id = email
        self.email = email
        self.username = name or email.split('@')[0]
        self.role = role

# In-memory session store
active_users = {}

@login_manager.user_loader
def load_user(email):
    if email in active_users:
        return active_users[email]
    # Reload from file if session exists but server restarted
    users = load_registered_users()
    if email in users:
        user = User(email, users[email].get('name', ''), users[email].get('role', 'analyst'))
        active_users[email] = user
        return user
    return None

@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith('/api/') or '/api/' in request.path:
        return jsonify({'success': False, 'error': 'Authentication required. Please login.'}), 401
    if request.path.startswith('/hub'):
        prefix = request.headers.get('X-Forwarded-Prefix', '')
        return redirect(f'{prefix}/hub/login')
    return redirect(url_for('login', next=request.url))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        users = load_registered_users()
        if email in users and users[email]['password'] == hash_password(password):
            user = User(email, users[email].get('name', ''), users[email].get('role', 'analyst'))
            active_users[email] = user
            login_user(user)
            print(f"✓ User logged in: {email}")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            error = 'Invalid email or password'
            print(f"✗ Login failed: {email}")

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    error = None
    success = None

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not email or not password:
            error = 'Email and password are required'
        elif password != confirm:
            error = 'Passwords do not match'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters'
        elif email not in load_allowed_emails():
            error = 'This email is not authorized. Please contact your admin to request access.'
        else:
            users = load_registered_users()
            if email in users:
                error = 'This email is already registered. Please login instead.'
            else:
                role = 'admin' if email in load_admin_emails() else 'analyst'
                users[email] = {
                    'name': name or email.split('@')[0],
                    'password': hash_password(password),
                    'role': role,
                    'registered_at': datetime.now().isoformat()
                }
                save_registered_users(users)
                success = 'Registration successful! You can now login.'
                print(f"✓ New user registered: {email}")

    return render_template('register.html', error=error, success=success)

@app.route('/logout')
@login_required
def logout():
    email = current_user.email
    active_users.pop(email, None)
    logout_user()
    print(f"✓ User logged out: {email}")
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET'])
@login_required
def admin_panel():
    if current_user.role != 'admin':
        return 'Access denied. Admin only.', 403
    allowed = load_allowed_emails()
    admins = load_admin_emails()
    users = load_registered_users()
    return render_template('admin.html', allowed_emails=allowed, admin_emails=admins, registered_users=users)

@app.route('/admin/add-email', methods=['POST'])
@login_required
def admin_add_email():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    email = request.form.get('email', '').strip().lower()
    is_admin = request.form.get('is_admin') == 'on'
    if not email:
        return redirect(url_for('admin_panel'))

    allowed = load_allowed_emails()
    admins = load_admin_emails()
    if email not in allowed:
        allowed.append(email)
    if is_admin and email not in admins:
        admins.append(email)
    save_whitelist(allowed, admins)
    print(f"✓ Admin added email: {email} (admin={is_admin})")
    return redirect(url_for('admin_panel'))

@app.route('/admin/remove-email', methods=['POST'])
@login_required
def admin_remove_email():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    email = request.form.get('email', '').strip().lower()
    if email == current_user.email:
        return redirect(url_for('admin_panel'))  # Can't remove yourself

    allowed = load_allowed_emails()
    admins = load_admin_emails()
    if email in allowed:
        allowed.remove(email)
    if email in admins:
        admins.remove(email)
    save_whitelist(allowed, admins)

    # Also remove from registered users
    users = load_registered_users()
    if email in users:
        del users[email]
        save_registered_users(users)

    print(f"✓ Admin removed email: {email}")
    return redirect(url_for('admin_panel'))

# Custom JSON provider to handle NaN, Inf, Decimal, numpy types
import numpy as np
from decimal import Decimal
from flask.json.provider import DefaultJSONProvider

class SafeJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            f = float(obj)
            return None if np.isnan(f) or np.isinf(f) else f
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

app.json_provider_class = SafeJSONProvider
app.json = SafeJSONProvider(app)

# Initialize AI Query Generator (optional - will only work if API key is set)
try:
    ai_generator = AIQueryGenerator()
    # AI Analyst will be initialized later with execute_query function
    ai_analyst = None
    AI_ENABLED = True
    print("✓ AI Query Generator initialized")
except Exception as e:
    ai_generator = None
    ai_analyst = None
    AI_ENABLED = False
    print(f"⚠ AI Query Generator not available: {e}")

def get_db_connection():
    """Create and return a database connection (MySQL or Databricks)"""
    try:
        if Config.DB_TYPE == 'databricks':
            connection = databricks_sql.connect(
                server_hostname=Config.DATABRICKS_CONFIG['server_hostname'],
                http_path=Config.DATABRICKS_CONFIG['http_path'],
                access_token=Config.DATABRICKS_CONFIG['access_token']
            )
            return connection
        else:  # MySQL
            connection = mysql.connector.connect(**Config.DB_CONFIG)
            if connection.is_connected():
                return connection
    except Exception as e:
        print(f"Error connecting to {Config.DB_TYPE}: {e}")
        raise e

def execute_query(query, params=None):
    """Execute a query and return results as a pandas DataFrame"""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        start_time = datetime.now()

        if Config.DB_TYPE == 'databricks':
            cursor.execute(query)
            # Fetch results
            columns = [desc[0] for desc in cursor.description]
            results = cursor.fetchall()
            # Convert to list of dicts
            results = [dict(zip(columns, row)) for row in results]
        else:  # MySQL
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query, params or ())
            results = cursor.fetchall()

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        # Convert to DataFrame and clean NaN/Inf values for JSON serialization
        df = pd.DataFrame(results)
        if not df.empty:
            import numpy as np
            df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

        return {
            'success': True,
            'data': df.to_dict('records') if not df.empty else [],
            'columns': df.columns.tolist() if not df.empty else [],
            'row_count': len(df),
            'execution_time': execution_time,
            'query': query
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'query': query
        }
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/')
@login_required
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/analyst')
@login_required
def analyst():
    """Render the AI Analyst interface"""
    return render_template('analyst.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Render the Data Dashboard - visual analytics interface"""
    return render_template('dashboard.html')

@app.route('/api/test-connection', methods=['GET'])
@login_required
def test_connection():
    """Test database connection"""
    try:
        connection = get_db_connection()

        if Config.DB_TYPE == 'databricks':
            # Test with a simple query
            cursor = connection.cursor()
            cursor.execute("SELECT current_version()")
            version = cursor.fetchone()[0]
            cursor.close()
            connection.close()
            return jsonify({
                'success': True,
                'message': f'Connected to Databricks (Runtime: {version})',
                'db_type': 'databricks'
            })
        else:  # MySQL
            if connection.is_connected():
                db_info = connection.get_server_info()
                connection.close()
                return jsonify({
                    'success': True,
                    'message': f'Connected to MySQL Server version {db_info}',
                    'db_type': 'mysql'
                })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'db_type': Config.DB_TYPE
        }), 500

@app.route('/api/execute-query', methods=['POST'])
@login_required
def execute_query_endpoint():
    """Execute a SQL query and return results"""
    data = request.get_json()
    query = data.get('query', '').strip()

    if not query:
        return jsonify({
            'success': False,
            'error': 'No query provided'
        }), 400

    # Basic validation - prevent multiple statements
    if ';' in query[:-1]:  # Allow semicolon at the end
        return jsonify({
            'success': False,
            'error': 'Multiple statements not allowed'
        }), 400

    result = execute_query(query)
    return jsonify(result)

@app.route('/api/generate-chart', methods=['POST'])
@login_required
def generate_chart():
    """Generate a chart from query results"""
    data = request.get_json()
    chart_data = data.get('data', [])
    chart_type = data.get('chart_type', 'bar')
    x_column = data.get('x_column')
    y_column = data.get('y_column')

    if not chart_data or not x_column or not y_column:
        return jsonify({
            'success': False,
            'error': 'Missing required data or column specifications'
        }), 400

    try:
        df = pd.DataFrame(chart_data)

        # Create chart based on type
        if chart_type == 'bar':
            fig = px.bar(df, x=x_column, y=y_column, title=f'{y_column} by {x_column}')
        elif chart_type == 'line':
            fig = px.line(df, x=x_column, y=y_column, title=f'{y_column} over {x_column}')
        elif chart_type == 'pie':
            fig = px.pie(df, names=x_column, values=y_column, title=f'{y_column} distribution')
        elif chart_type == 'scatter':
            fig = px.scatter(df, x=x_column, y=y_column, title=f'{y_column} vs {x_column}')
        else:
            return jsonify({
                'success': False,
                'error': f'Unsupported chart type: {chart_type}'
            }), 400

        # Convert to JSON
        chart_json = json.loads(fig.to_json())

        return jsonify({
            'success': True,
            'chart': chart_json
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/saved-queries', methods=['GET'])
@login_required
def get_saved_queries():
    """Get list of saved/base queries"""
    # You can expand this to read from a file or database
    base_queries = [
        {
            'name': 'STAR Daily FTD Summary',
            'description': 'Daily first-time deposits for STAR brand',
            'query': 'SELECT date, SUM(ftd) as total_ftd, SUM(ftd_amount) as total_amount FROM gbis.biz.dashboard_star_fact_daily_kpi WHERE date >= DATE_SUB(CURRENT_DATE(), 30) GROUP BY date ORDER BY date DESC'
        },
        {
            'name': 'STAR Sales Performance',
            'description': 'Sales team performance metrics',
            'query': 'SELECT sales_name, SUM(ftd) as ftd, SUM(gross_deposit) as deposits, SUM(trading_volume) as volume FROM gbis.biz.dashboard_star_sales_metrics_daily WHERE date >= DATE_SUB(CURRENT_DATE(), 7) GROUP BY sales_name ORDER BY ftd DESC LIMIT 10'
        }
    ]
    return jsonify({'queries': base_queries})

@app.route('/api/ai/status', methods=['GET'])
@login_required
def ai_status():
    """Check if AI query generation is available"""
    return jsonify({
        'enabled': AI_ENABLED,
        'message': 'AI query generation is available' if AI_ENABLED else 'ANTHROPIC_API_KEY not configured'
    })

@app.route('/api/ai/generate-query', methods=['POST'])
@login_required
def ai_generate_query():
    """Generate SQL query from natural language"""
    if not AI_ENABLED:
        return jsonify({
            'success': False,
            'error': 'AI query generation not available. Please set ANTHROPIC_API_KEY in .env file'
        }), 503

    data = request.get_json()
    natural_language = data.get('question', '').strip()

    if not natural_language:
        return jsonify({
            'success': False,
            'error': 'No question provided'
        }), 400

    try:
        result = ai_generator.generate_query(natural_language)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/ai/analyze-data', methods=['POST'])
@login_required
def ai_analyze_data():
    """Analyze query results with AI"""
    if not AI_ENABLED:
        return jsonify({
            'success': False,
            'error': 'AI analysis not available. Please set ANTHROPIC_API_KEY in .env file'
        }), 503

    data = request.get_json()
    query = data.get('query', '')
    query_data = data.get('data', [])
    question = data.get('question', '')

    if not query or not query_data:
        return jsonify({
            'success': False,
            'error': 'Missing query or data'
        }), 400

    try:
        result = ai_generator.analyze_data(query, query_data, question)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/ai/refine-query', methods=['POST'])
@login_required
def ai_refine_query():
    """Refine a failed query based on error"""
    if not AI_ENABLED:
        return jsonify({
            'success': False,
            'error': 'AI query refinement not available'
        }), 503

    data = request.get_json()
    original_query = data.get('query', '')
    error_message = data.get('error', '')
    natural_language = data.get('question', '')

    if not original_query or not error_message:
        return jsonify({
            'success': False,
            'error': 'Missing query or error message'
        }), 400

    try:
        result = ai_generator.refine_query(original_query, error_message, natural_language)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/ai/comprehensive-analysis', methods=['POST'])
@login_required
def comprehensive_analysis():
    """Perform comprehensive AI analysis with multiple queries and visualizations"""
    if not AI_ENABLED:
        return jsonify({
            'success': False,
            'error': 'AI Analyst not available. Please configure ANTHROPIC_API_KEY or AWS Bedrock'
        }), 503

    data = request.get_json()
    question = data.get('question', '').strip()
    language = data.get('language', 'en')  # 'en' or 'zh'

    if not question:
        return jsonify({
            'success': False,
            'error': 'No question provided'
        }), 400

    try:
        # Initialize AI analyst with execute_query function
        analyst = AIAnalystAgent(execute_query_fn=execute_query)
        result = analyst.analyze(question, language=language)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/dashboard/visualize', methods=['POST'])
@login_required
def dashboard_visualize():
    """Generate a visualization from a natural language question.
    Flow: generate SQL → execute → auto-pick chart type → return plot JSON."""
    if not AI_ENABLED:
        return jsonify({
            'success': False,
            'error': 'AI not available. Please configure ANTHROPIC_API_KEY or AWS Bedrock'
        }), 503

    data = request.get_json()
    question = data.get('question', '').strip()

    if not question:
        return jsonify({'success': False, 'error': 'No question provided'}), 400

    try:
        # Step 1: Generate SQL from natural language
        gen_result = ai_generator.generate_query(question)
        if not gen_result.get('success'):
            return jsonify({
                'success': False,
                'error': gen_result.get('error', 'Failed to generate query')
            })

        sql = gen_result['sql']

        # Step 2: Execute the query
        query_result = execute_query(sql)
        if not query_result.get('success'):
            # Try to refine once on failure
            refined = ai_generator.refine_query(sql, query_result.get('error', ''), question)
            if refined.get('success') and refined.get('sql'):
                query_result = execute_query(refined['sql'])
                if not query_result.get('success'):
                    return jsonify({
                        'success': False,
                        'error': f"Query failed: {query_result.get('error')}"
                    })
                sql = refined['sql']
            else:
                return jsonify({
                    'success': False,
                    'error': f"Query failed: {query_result.get('error')}"
                })

        if not query_result.get('data'):
            return jsonify({
                'success': False,
                'error': 'Query returned no data'
            })

        # Step 3: Auto-pick chart type and build visualization
        df = pd.DataFrame(query_result['data'])
        columns = query_result['columns']

        # Use AI suggestion as a hint
        suggested_chart = gen_result.get('suggested_chart')
        suggested_x = gen_result.get('x_column')
        suggested_y = gen_result.get('y_column')

        chart_info = _auto_pick_chart(df, columns, suggested_chart, suggested_x, suggested_y)

        # Step 4: Create Plotly figure
        fig = _create_auto_chart(df, chart_info, question)
        if fig is None:
            return jsonify({
                'success': False,
                'error': 'Could not generate a suitable visualization for this data'
            })

        chart_json = json.loads(fig.to_json())

        return jsonify({
            'success': True,
            'chart': chart_json,
            'chart_type': chart_info['type'],
            'title': chart_info.get('title', question),
            'row_count': query_result['row_count'],
            'execution_time': query_result.get('execution_time', 0)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _auto_pick_chart(df, columns, suggested_type=None, suggested_x=None, suggested_y=None):
    """Determine the best chart type based on data characteristics."""
    import numpy as np

    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    non_num_cols = [c for c in columns if c not in num_cols]

    # Try to detect date columns
    date_cols = []
    for c in columns:
        if any(kw in c.lower() for kw in ['date', 'day', 'week', 'month', 'year', 'time', 'period']):
            date_cols.append(c)

    cat_cols = [c for c in non_num_cols if c not in date_cols]

    # Validate AI suggestions exist in data
    x_col = suggested_x if suggested_x in columns else None
    y_col = suggested_y if suggested_y in columns else None

    # If AI suggested valid columns and chart type, use them
    if suggested_type and x_col and y_col:
        color_col = None
        if cat_cols and suggested_type in ('bar', 'line'):
            candidate = [c for c in cat_cols if c != x_col and c != y_col]
            if candidate and df[candidate[0]].nunique() <= 10:
                color_col = candidate[0]
        return {
            'type': suggested_type,
            'x': x_col,
            'y': y_col,
            'color': color_col,
            'title': f'{y_col} by {x_col}'
        }

    # Auto-detection logic
    # Case 1: Has date column + numeric → line chart
    if date_cols and num_cols:
        x = date_cols[0]
        y = num_cols[0]
        color = None
        if cat_cols and df[cat_cols[0]].nunique() <= 10:
            color = cat_cols[0]
        return {'type': 'line', 'x': x, 'y': y, 'color': color, 'title': f'{y} over {x}'}

    # Case 2: One categorical + one numeric + few categories → pie chart
    if len(cat_cols) >= 1 and len(num_cols) >= 1 and df[cat_cols[0]].nunique() <= 8:
        return {'type': 'pie', 'x': cat_cols[0], 'y': num_cols[0], 'color': None,
                'title': f'{num_cols[0]} distribution by {cat_cols[0]}'}

    # Case 3: Categorical + numeric → bar chart
    if cat_cols and num_cols:
        x = cat_cols[0]
        y = num_cols[0]
        color = None
        if len(cat_cols) > 1 and df[cat_cols[1]].nunique() <= 10:
            color = cat_cols[1]
        return {'type': 'bar', 'x': x, 'y': y, 'color': color, 'title': f'{y} by {x}'}

    # Case 4: Two numeric columns → scatter
    if len(num_cols) >= 2:
        return {'type': 'scatter', 'x': num_cols[0], 'y': num_cols[1], 'color': None,
                'title': f'{num_cols[1]} vs {num_cols[0]}'}

    # Fallback: bar chart with first two columns
    if len(columns) >= 2:
        return {'type': 'bar', 'x': columns[0], 'y': columns[1], 'color': None,
                'title': f'{columns[1]} by {columns[0]}'}

    return {'type': 'bar', 'x': columns[0], 'y': columns[0], 'color': None, 'title': question}


def _create_auto_chart(df, chart_info, question):
    """Create a Plotly figure based on auto-picked chart config."""
    try:
        chart_type = chart_info['type']
        x = chart_info['x']
        y = chart_info['y']
        color = chart_info.get('color')
        title = chart_info.get('title', question)

        if chart_type == 'line':
            fig = px.line(df, x=x, y=y, color=color, title=title,
                          template='plotly_white', markers=True)
        elif chart_type == 'bar':
            fig = px.bar(df, x=x, y=y, color=color, title=title,
                         template='plotly_white',
                         barmode='group' if color else 'relative')
        elif chart_type == 'pie':
            fig = px.pie(df, names=x, values=y, title=title, template='plotly_white')
        elif chart_type == 'scatter':
            fig = px.scatter(df, x=x, y=y, color=color, title=title,
                             template='plotly_white')
        else:
            fig = px.bar(df, x=x, y=y, title=title, template='plotly_white')

        fig.update_layout(
            font=dict(size=13),
            title_font_size=16,
            showlegend=True,
            height=500
        )
        return fig
    except Exception as e:
        print(f"Chart creation error: {e}")
        return None


@app.route('/api/ai/translate-insights', methods=['POST'])
@login_required
def translate_insights():
    """Translate analysis insights to target language"""
    if not AI_ENABLED:
        return jsonify({
            'success': False,
            'error': 'AI translation not available'
        }), 503

    data = request.get_json()
    insights = data.get('insights', '').strip()
    analysis_approach = data.get('analysis_approach', '').strip()
    target_language = data.get('target_language', 'en')

    if not insights:
        return jsonify({
            'success': False,
            'error': 'No content to translate'
        }), 400

    try:
        # Initialize AI analyst
        analyst = AIAnalystAgent(execute_query_fn=execute_query)
        translated = analyst.translate_text(insights, analysis_approach, target_language)
        return jsonify(translated)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==========================================
# Lark Bot Webhook
# ==========================================
from lark_bot import handle_lark_event, LARK_VERIFICATION_TOKEN

@app.route('/lark/webhook', methods=['POST'])
def lark_webhook():
    """Lark event subscription endpoint."""
    body = request.json

    # Token verification
    token = body.get('token') or body.get('header', {}).get('token', '')
    if LARK_VERIFICATION_TOKEN and token != LARK_VERIFICATION_TOKEN:
        return jsonify({'error': 'invalid token'}), 403

    result = handle_lark_event(body)
    return jsonify(result)


@app.route('/lark/card_action', methods=['GET', 'POST'])
def lark_card_action():
    """Lark card action callback — handles verification + button clicks."""
    # GET request — simple health check for Lark verification
    if request.method == 'GET':
        return jsonify({'success': True})

    body = request.json or {}

    # Lark URL verification challenge (multiple formats)
    if 'challenge' in body:
        return jsonify({'challenge': body['challenge']})
    if body.get('type') == 'url_verification':
        return jsonify({'challenge': body.get('challenge', '')})

    # Card action event
    action = body.get('action', {})
    value = action.get('value', {})

    if value.get('action') == 'digest_feedback':
        rating = value.get('rating', '')
        open_id = body.get('open_id', '')
        hub_logger.log_request({
            'type': 'digest_feedback',
            'rating': rating,
            'open_id': open_id,
            'timestamp': datetime.now().isoformat()
        })
        return jsonify({'toast': {'type': 'success', 'content': '感谢反馈！'}})

    return jsonify({})


@app.route('/hub/api/digest-feedback', methods=['GET'])
def digest_feedback():
    """Record digest feedback via URL click (no Lark card callback needed)."""
    token = request.args.get('token', '')
    rating = request.args.get('rating', '')

    if token not in DIGEST_AUTO_TOKENS:
        return '<h3>无效链接</h3>', 403
    if rating not in ('good', 'bad'):
        return '<h3>无效评分</h3>', 400

    email = DIGEST_AUTO_TOKENS[token]
    hub_logger.log_request({
        'type': 'digest_feedback',
        'rating': rating,
        'user': email,
        'timestamp': datetime.now().isoformat()
    })

    msg = '感谢反馈！你的评价已记录。' if rating == 'good' else '感谢反馈！我们会改进推送内容。'
    return f'<html><body style="font-family:sans-serif;text-align:center;padding:60px;"><h2>{msg}</h2><p>可以关闭此页面了</p></body></html>'


# ==========================================
# Executive Chatbot Routes
# ==========================================
from chat_engine import ChatEngine, load_conversations, save_conversations
import uuid

chat_engine = ChatEngine()


@app.route('/chat')
@app.route('/chat/')
def chat_index():
    return render_template('chat.html')


@app.route('/chat/api/send', methods=['POST'])
def chat_send():
    data = request.json
    message = data.get('message', '').strip()
    conversation_id = data.get('conversation_id')

    if not message:
        return jsonify({'error': 'Empty message'}), 400

    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    conversations = load_conversations()

    if conversation_id not in conversations:
        conversations[conversation_id] = []

    conversations[conversation_id].append({
        'role': 'user',
        'content': message,
        'timestamp': datetime.now().isoformat()
    })

    history = conversations[conversation_id]

    try:
        response = chat_engine.chat(message, history[:-1])
        conversations[conversation_id].append({
            'role': 'assistant',
            'content': response['answer'],
            'sql': response.get('sql'),
            'data': response.get('data'),
            'chart': response.get('chart'),
            'timestamp': datetime.now().isoformat()
        })
        save_conversations(conversations)
        return jsonify({
            'conversation_id': conversation_id,
            'answer': response['answer'],
            'sql': response.get('sql'),
            'data': response.get('data'),
            'chart': response.get('chart'),
            'suggestions': response.get('suggestions')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/chat/api/feedback', methods=['POST'])
def chat_feedback():
    data = request.json
    rating = data.get('rating')
    if not rating or rating not in ('good', 'bad'):
        return jsonify({'error': 'Invalid rating'}), 400

    hub_logger.log_request({
        'type': 'feedback',
        'conversation_id': data.get('conversation_id'),
        'rating': rating,
        'user': current_user.id if current_user.is_authenticated else None
    })
    return jsonify({'ok': True})


@app.route('/chat/api/conversations', methods=['GET'])
def chat_list_conversations():
    conversations = load_conversations()
    result = []
    for cid, msgs in conversations.items():
        if msgs:
            result.append({
                'id': cid,
                'preview': msgs[0]['content'][:50],
                'updated': msgs[-1]['timestamp']
            })
    result.sort(key=lambda x: x['updated'], reverse=True)
    return jsonify(result)


@app.route('/chat/api/conversations/<conversation_id>', methods=['GET'])
def chat_get_conversation(conversation_id):
    conversations = load_conversations()
    msgs = conversations.get(conversation_id, [])
    return jsonify(msgs)


@app.route('/chat/api/conversations/<conversation_id>', methods=['DELETE'])
def chat_delete_conversation(conversation_id):
    conversations = load_conversations()
    conversations.pop(conversation_id, None)
    save_conversations(conversations)
    return jsonify({'ok': True})


# ==========================================
# AI Hub Routes (unified entry with routing)
# ==========================================
from hub_router import HubRouter
from external_data_agent import ExternalDataAgent
from external_news_agent import ExternalNewsAgent
from hub_logger import HubLogger
from user_memory import UserMemory

hub_router = HubRouter()
external_agent = ExternalDataAgent()
news_agent = ExternalNewsAgent()
hub_logger = HubLogger()
user_memory = UserMemory(bedrock_client=hub_router.bedrock)

HUB_CONVERSATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hub_history.json')


def load_hub_conversations():
    if os.path.exists(HUB_CONVERSATIONS_FILE):
        with open(HUB_CONVERSATIONS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_hub_conversations(convs):
    with open(HUB_CONVERSATIONS_FILE, 'w') as f:
        json.dump(convs, f, ensure_ascii=False, default=str)


@app.route('/hub/login', methods=['GET', 'POST'])
def hub_login():
    if current_user.is_authenticated:
        prefix = request.headers.get('X-Forwarded-Prefix', '')
        return redirect(f'{prefix}/hub')

    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        users = load_registered_users()
        if email in users and users[email]['password'] == hash_password(password):
            user = User(email, users[email].get('name', ''), users[email].get('role', 'analyst'))
            active_users[email] = user
            login_user(user)
            prefix = request.headers.get('X-Forwarded-Prefix', '')
            return redirect(f'{prefix}/hub')
        else:
            error = 'Invalid email or password'

    return render_template('hub_login.html', error=error)


@app.route('/hub/register', methods=['GET', 'POST'])
def hub_register():
    if current_user.is_authenticated:
        prefix = request.headers.get('X-Forwarded-Prefix', '')
        return redirect(f'{prefix}/hub')

    error = None
    success = None

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not email or not password:
            error = 'Email and password are required'
        elif password != confirm:
            error = 'Passwords do not match'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters'
        elif email not in load_allowed_emails():
            error = 'This email is not authorized. Please contact admin.'
        else:
            users = load_registered_users()
            if email in users:
                error = 'This email is already registered. Please login.'
            else:
                role = 'admin' if email in load_admin_emails() else 'analyst'
                users[email] = {
                    'name': name or email.split('@')[0],
                    'password': hash_password(password),
                    'role': role,
                    'registered_at': datetime.now().isoformat()
                }
                save_registered_users(users)
                success = 'Registration successful! You can now login.'

    return render_template('hub_register.html', error=error, success=success)


@app.route('/hub/admin', methods=['GET'])
@login_required
def hub_admin_panel():
    if current_user.role != 'admin':
        return 'Access denied. Admin only.', 403
    allowed = load_allowed_emails()
    admins = load_admin_emails()
    users = load_registered_users()
    return render_template('hub_admin.html', allowed_emails=allowed, admin_emails=admins, registered_users=users)


@app.route('/hub/admin/add-email', methods=['POST'])
@login_required
def hub_admin_add_email():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    email = request.form.get('email', '').strip().lower()
    is_admin = request.form.get('is_admin') == 'on'
    prefix = request.headers.get('X-Forwarded-Prefix', '')
    if not email:
        return redirect(f'{prefix}/hub/admin')

    allowed = load_allowed_emails()
    admins = load_admin_emails()
    if email not in allowed:
        allowed.append(email)
    if is_admin and email not in admins:
        admins.append(email)
    save_whitelist(allowed, admins)
    return redirect(f'{prefix}/hub/admin')


@app.route('/hub/admin/remove-email', methods=['POST'])
@login_required
def hub_admin_remove_email():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    prefix = request.headers.get('X-Forwarded-Prefix', '')
    email = request.form.get('email', '').strip().lower()
    if email == current_user.email:
        return redirect(f'{prefix}/hub/admin')

    allowed = load_allowed_emails()
    admins = load_admin_emails()
    if email in allowed:
        allowed.remove(email)
    if email in admins:
        admins.remove(email)
    save_whitelist(allowed, admins)

    users = load_registered_users()
    if email in users:
        del users[email]
        save_registered_users(users)

    return redirect(f'{prefix}/hub/admin')


# Auto-login via token (for Lark digest links)
DIGEST_AUTO_TOKENS = {
    'yDTsLSsMoW54xZRrWY1bks7EjMhjNiea': 'kevin.liu@hytechc.com'
}


@app.before_request
def auto_login_by_token():
    if current_user.is_authenticated:
        return
    token = request.args.get('token')
    if token and token in DIGEST_AUTO_TOKENS:
        email = DIGEST_AUTO_TOKENS[token]
        users = load_registered_users()
        if email in users:
            user = User(email, users[email].get('name', ''), users[email].get('role', 'analyst'))
            active_users[email] = user
            login_user(user)


@app.route('/hub')
@app.route('/hub/')
@login_required
def hub_index():
    is_admin = current_user.role == 'admin'
    user_name = current_user.username
    user_initial = user_name[0].upper() if user_name else 'U'
    return render_template('hub.html', is_admin=is_admin, user_name=user_name, user_initial=user_initial)


@app.route('/hub/api/send', methods=['POST'])
@login_required
def hub_send():
    data = request.json
    message = data.get('message', '').strip()
    conversation_id = data.get('conversation_id')

    if not message:
        return jsonify({'error': 'Empty message'}), 400

    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    # Start logging
    req_log = hub_logger.start(message, current_user.id if current_user.is_authenticated else None)

    # Route the question
    route_result = hub_router.route(message)
    agent = route_result.get('agent', 'internal_data')

    # Record to user memory
    user_memory.record_question(current_user.id, message, agent)
    req_log.set_route(agent, route_result.get('confidence'))

    conversations = load_hub_conversations()
    if conversation_id not in conversations:
        conversations[conversation_id] = []

    conversations[conversation_id].append({
        'role': 'user',
        'content': message,
        'timestamp': datetime.now().isoformat()
    })

    history = conversations[conversation_id]

    try:
        if agent == 'internal_data':
            response = chat_engine.chat(message, history[:-1])
            agent_label = 'internal'
        elif agent == 'external_social':
            response = external_agent.chat(message, history[:-1])
            agent_label = 'external_social'
        elif agent == 'external_news':
            response = news_agent.chat(message, history[:-1])
            agent_label = 'external_news'
        elif agent == 'external_data':
            response = external_agent.chat(message, history[:-1])
            agent_label = 'external_social'
        else:
            response = chat_engine.chat(message, history[:-1])
            agent_label = 'internal'

        req_log.set_response(response, agent_label)
        req_log.save()

        conversations[conversation_id].append({
            'role': 'assistant',
            'content': response['answer'],
            'sql': response.get('sql'),
            'data': response.get('data'),
            'chart': response.get('chart'),
            'timestamp': datetime.now().isoformat()
        })
        save_hub_conversations(conversations)

        return jsonify({
            'conversation_id': conversation_id,
            'answer': response['answer'],
            'sql': response.get('sql'),
            'data': response.get('data'),
            'chart': response.get('chart'),
            'suggestions': response.get('suggestions'),
            'agent': agent_label
        })
    except Exception as e:
        req_log.set_error(e)
        req_log.save()
        return jsonify({'error': str(e)}), 500


def _external_data_placeholder(message):
    """Placeholder for external data agent — to be replaced with real endpoint."""
    return {
        'answer': '外部数据分析功能正在开发中，即将上线。\n\n您的问题已记录，待外部数据引擎接入后将自动支持此类分析。',
        'sql': None,
        'data': None,
        'chart': None,
        'suggestions': [
            '切换到内部数据：各品牌本月NRFR表现',
            '切换到内部数据：本季度目标完成度排名',
            '切换到内部数据：VT近期TDAU趋势'
        ]
    }


@app.route('/hub/api/feedback', methods=['POST'])
@login_required
def hub_feedback():
    data = request.json
    conversation_id = data.get('conversation_id')
    rating = data.get('rating')
    if not rating or rating not in ('good', 'bad'):
        return jsonify({'error': 'Invalid rating'}), 400

    # Find the last user question in this conversation for memory
    last_question = None
    if conversation_id:
        convs = load_hub_conversations()
        msgs = convs.get(conversation_id, [])
        for msg in reversed(msgs):
            if msg.get('role') == 'user':
                last_question = msg.get('content', '')
                break

    hub_logger.log_request({
        'type': 'feedback',
        'conversation_id': conversation_id,
        'rating': rating,
        'user': current_user.id if current_user.is_authenticated else None
    })

    # Record feedback to user memory
    if last_question:
        user_memory.record_feedback(current_user.id, last_question, rating)

    return jsonify({'ok': True})


@app.route('/hub/api/conversations', methods=['GET'])
@login_required
def hub_list_conversations():
    conversations = load_hub_conversations()
    result = []
    for cid, msgs in conversations.items():
        if msgs:
            result.append({
                'id': cid,
                'preview': msgs[0]['content'][:50],
                'updated': msgs[-1]['timestamp']
            })
    result.sort(key=lambda x: x['updated'], reverse=True)
    return jsonify(result)


@app.route('/hub/api/conversations/<conversation_id>', methods=['GET'])
@login_required
def hub_get_conversation(conversation_id):
    conversations = load_hub_conversations()
    msgs = conversations.get(conversation_id, [])
    return jsonify(msgs)


@app.route('/hub/api/conversations/<conversation_id>', methods=['DELETE'])
@login_required
def hub_delete_conversation(conversation_id):
    conversations = load_hub_conversations()
    conversations.pop(conversation_id, None)
    save_hub_conversations(conversations)
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
