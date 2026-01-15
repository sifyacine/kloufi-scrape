import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """
    Global configuration for the scraping project.
    Supports both development and production environments.
    """
    # Environment
    ENV = os.getenv('ENV', 'development')  # 'development' or 'production'
    
    # Browser Settings
    HEADLESS = os.getenv('HEADLESS', 'True').lower() == 'true'
    BROWSER_TYPE = os.getenv('BROWSER_TYPE', 'chromium')
    USER_AGENT = os.getenv('USER_AGENT', 
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
    
    # Crawl4AI Specifics
    VERBOSE = os.getenv('VERBOSE', 'True').lower() == 'true'
    CACHE_MODE = os.getenv('CACHE_MODE', 'BYPASS')
    
    # Timeouts (in milliseconds)
    PAGE_TIMEOUT = int(os.getenv('PAGE_TIMEOUT', 60000))
    DELAY_BEFORE_RETURN_HTML = int(os.getenv('DELAY_BEFORE_RETURN_HTML', 2000))
    
    # Retry Logic
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
    RETRY_DELAY = int(os.getenv('RETRY_DELAY', 5))
    
    # Scraping Limits
    # Set to None for production (unlimited), or a number for testing
    MAX_ITEMS = 10  # Set to 10 for testing data quality
    
    # Category (for single-category deployment)
    CATEGORY = os.getenv('CATEGORY', 'voiture')
    
    # Continuous Running
    LOOP_MODE = os.getenv('LOOP_MODE', 'False').lower() == 'true'
    LOOP_INTERVAL = int(os.getenv('LOOP_INTERVAL', 21600))  # 6 hours in seconds
    
    # Output Paths
    DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.getcwd(), "data"))
    LOGS_DIR = os.getenv('LOGS_DIR', os.path.join(os.getcwd(), "logs"))
    
    # Elasticsearch
    ES_ENABLED = os.getenv('ES_ENABLED', 'True').lower() == 'true'
    ES_HOST = os.getenv('ELASTICSEARCH_HOST', 'localhost')
    ES_PORT = int(os.getenv('ELASTICSEARCH_PORT', 9200))
    ES_USERNAME = os.getenv('ELASTICSEARCH_USERNAME', '')
    ES_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD', '')
    ES_USE_SSL = os.getenv('ES_USE_SSL', 'False').lower() == 'true'
    ES_VERIFY_CERTS = os.getenv('ES_VERIFY_CERTS', 'False').lower() == 'true'
    
    # Notifications
    ENABLE_ALERTS = os.getenv('ENABLE_ALERTS', 'False').lower() == 'true'
    ALERT_EMAIL = os.getenv('ALERT_EMAIL', '')
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')

    @staticmethod
    def ensure_dirs():
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        os.makedirs(Config.LOGS_DIR, exist_ok=True)
    
    @staticmethod
    def is_production():
        return Config.ENV == 'production'
    
    @staticmethod
    def get_es_connection_string():
        protocol = 'https' if Config.ES_USE_SSL else 'http'
        return f"{protocol}://{Config.ES_HOST}:{Config.ES_PORT}"
