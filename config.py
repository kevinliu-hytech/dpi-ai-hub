import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'True') == 'True'
    SESSION_COOKIE_PATH = '/'
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Database Type
    DB_TYPE = os.getenv('DB_TYPE', 'mysql').lower()

    # MySQL Database
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 3306)),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'metrics_db'),
        'charset': 'utf8mb4',
        'use_unicode': True
    }

    # Databricks Configuration
    DATABRICKS_CONFIG = {
        'server_hostname': os.getenv('DATABRICKS_SERVER_HOSTNAME', ''),
        'http_path': os.getenv('DATABRICKS_HTTP_PATH', ''),
        'access_token': os.getenv('DATABRICKS_ACCESS_TOKEN', ''),
        'catalog': os.getenv('DATABRICKS_CATALOG', 'gbis'),
        'schema': os.getenv('DATABRICKS_SCHEMA', 'biz')
    }

    # AWS Region (for Bedrock)
    AWS_REGION = os.getenv('AWS_REGION', 'ap-southeast-1')

    # Lark Bot
    LARK_APP_ID = os.getenv('LARK_APP_ID', '')
    LARK_APP_SECRET = os.getenv('LARK_APP_SECRET', '')
    LARK_VERIFICATION_TOKEN = os.getenv('LARK_VERIFICATION_TOKEN', '')
    LARK_ENCRYPT_KEY = os.getenv('LARK_ENCRYPT_KEY', '')

    # Query timeout (seconds)
    QUERY_TIMEOUT = 30

    # Max rows to return
    MAX_ROWS = 10000
