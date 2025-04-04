"""
Configuration for YouTrack API and application settings.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class YouTrackConfig:
    """Configuration for YouTrack API."""
    base_url: str = os.getenv("YOUTRACK_BASE_URL")
    token: str = os.getenv("YOUTRACK_TOKEN")
    project_id: str = "EISMMABSW"  # Use the correct project short name/key directly
    max_retries: int = int(os.getenv("YOUTRACK_MAX_RETRIES", 3))
    retry_delay: int = int(os.getenv("YOUTRACK_RETRY_DELAY", 2))  # seconds
    timeout: int = int(os.getenv("YOUTRACK_TIMEOUT", 60))  # seconds
    cache_ttl: int = 3600  # seconds
    issue_batch_size: int = int(os.getenv("YOUTRACK_ISSUE_BATCH_SIZE", 50))
    history_batch_size: int = int(os.getenv("YOUTRACK_HISTORY_BATCH_SIZE", 10))

@dataclass
class AppConfig:
    """Application configuration."""
    # Data storage paths
    data_dir: str = os.getenv("DATA_DIR", "data")
    issues_file: str = "issues.json"
    processed_data_file: str = os.getenv("PROCESSED_DATA_FILE", "processed_youtrack_data.json")
    raw_data_file: str = os.getenv("RAW_DATA_FILE", "raw_youtrack_data.json")
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Application settings
    refresh_interval: int = 3600  # seconds
    page_size: int = 50
    
    # Report settings
    report_output_dir: str = os.getenv("REPORT_DIR", "reports")
    streamlit_port: int = int(os.getenv("STREAMLIT_PORT", 8503))
    enable_report_saving: bool = os.getenv("ENABLE_REPORT_SAVING", "true").lower() == "true"

# Create config instances
youtrack_config = YouTrackConfig()
app_config = AppConfig()

# Ensure directories exist
os.makedirs(app_config.data_dir, exist_ok=True)
os.makedirs(app_config.report_output_dir, exist_ok=True)

# Basic validation
if not youtrack_config.base_url or not youtrack_config.token:
    raise ValueError("YOUTRACK_BASE_URL and YOUTRACK_TOKEN must be set in .env or environment variables.")

print(f"Log Level: {app_config.log_level}")

# --- Email Settings --- 
EMAIL_ENABLED = True 
REPORT_RECIPIENTS = ["rahipdotaci@gmail.com", "ahmetali@kayten.de"] # List of recipient email addresses
EMAIL_SUBJECT_PREFIX = "MQ EIS/KG BSW - Daily Intelligence Report"
