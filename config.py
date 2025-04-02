"""
Configuration for YouTrack API and application settings.
"""
import os
from dataclasses import dataclass

@dataclass
class YouTrackConfig:
    """Configuration for YouTrack API."""
    base_url: str = "https://youtrack.kayten.net"
    token: str = os.getenv(
        "YOUTRACK_TOKEN", 
        "perm-a2Fhbi5vemthbg==.NTgtMTU=.u5uaOfgc8R5zWFA1irSCpuf1z4XVUa"
    )
    project_id: str = "0-9"  # "MQ EIS/KG BSW (Mercedes)"
    max_retries: int = 3
    retry_delay: int = 2  # seconds
    timeout: int = 30  # seconds
    cache_ttl: int = 3600  # seconds

@dataclass
class AppConfig:
    """Application configuration."""
    # Data storage paths
    data_dir: str = "data"
    issues_file: str = "issues.json"
    processed_data_file: str = "processed_data.json"
    
    # Logging
    log_level: str = "INFO"
    
    # Application settings
    refresh_interval: int = 3600  # seconds
    page_size: int = 50
    
    # Report settings
    report_output_dir: str = "reports"

# Create config instances
youtrack_config = YouTrackConfig()
app_config = AppConfig()

# Ensure directories exist
os.makedirs(app_config.data_dir, exist_ok=True)
os.makedirs(app_config.report_output_dir, exist_ok=True)
