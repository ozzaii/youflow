"""
Utility functions for the YouTrack data extraction and analysis system.
"""
import os
import json
import datetime
import logging
import pandas as pd
from typing import Dict, Any, List, Optional, Union, Tuple
from pathlib import Path
import time

from config import app_config

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_data_freshness() -> Tuple[bool, Optional[float]]:
    """
    Check if the data is fresh or needs to be updated.
    
    Returns:
        Tuple of (is_fresh, age_in_hours)
    """
    issues_file_path = os.path.join(app_config.data_dir, app_config.issues_file)
    
    if not os.path.exists(issues_file_path):
        logger.info("No data file found, data needs to be extracted")
        return False, None
    
    # Get file modification time
    file_mod_time = os.path.getmtime(issues_file_path)
    current_time = time.time()
    
    # Calculate age in hours
    age_in_seconds = current_time - file_mod_time
    age_in_hours = age_in_seconds / 3600
    
    # Check if older than refresh interval
    is_fresh = age_in_hours < (app_config.refresh_interval / 3600)
    
    logger.info(f"Data age: {age_in_hours:.2f} hours, is fresh: {is_fresh}")
    
    return is_fresh, age_in_hours

def format_timedelta(td: datetime.timedelta) -> str:
    """
    Format a timedelta object as a readable string.
    
    Args:
        td: Timedelta object
        
    Returns:
        Formatted string (e.g., "3 days, 4 hours")
    """
    total_seconds = int(td.total_seconds())
    days = total_seconds // (24 * 3600)
    remainder = total_seconds % (24 * 3600)
    hours = remainder // 3600
    remainder %= 3600
    minutes = remainder // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} {'day' if days == 1 else 'days'}")
    if hours > 0:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes > 0 and days == 0:  # Only show minutes if less than a day
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    
    return ", ".join(parts) if parts else "less than a minute"

def get_custom_field_value(df: pd.DataFrame, issue_id: str, field_name: str) -> str:
    """
    Get the value of a custom field for a specific issue.
    
    Args:
        df: DataFrame containing custom field data
        issue_id: ID of the issue
        field_name: Name of the custom field
        
    Returns:
        Value of the custom field or empty string if not found
    """
    mask = (df['issue_id'] == issue_id) & (df['field_name'] == field_name)
    matching_rows = df[mask]
    
    if not matching_rows.empty:
        return matching_rows.iloc[0]['field_value']
    return ""

def generate_report_filename(report_type: str, format: str = 'html') -> str:
    """
    Generate a filename for a report.
    
    Args:
        report_type: Type of report
        format: File format
        
    Returns:
        Filename with timestamp
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{report_type}_report_{timestamp}.{format}"

def save_report(content: str, filename: str) -> str:
    """
    Save a report to the reports directory.
    
    Args:
        content: Report content
        filename: Filename for the report
        
    Returns:
        Full path to the saved report
    """
    os.makedirs(app_config.report_output_dir, exist_ok=True)
    full_path = os.path.join(app_config.report_output_dir, filename)
    
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"Report saved to {full_path}")
    return full_path

def create_html_report(title: str, content: List[Dict[str, Any]]) -> str:
    """
    Create an HTML report from the provided content.
    
    Args:
        title: Report title
        content: List of content blocks (each with 'type', 'title', and 'content' keys)
        
    Returns:
        HTML content as a string
    """
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }}
            h1 {{
                color: #0077C2;
                border-bottom: 2px solid #0077C2;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #0077C2;
                margin-top: 30px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #f2f2f2;
                font-weight: bold;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            .chart-container {{
                width: 100%;
                height: 400px;
                margin: 20px 0;
            }}
            .footer {{
                margin-top: 40px;
                border-top: 1px solid #ddd;
                padding-top: 10px;
                font-size: 0.8em;
                color: #777;
            }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        <p>Generated on: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    """
    
    for item in content:
        html += f"<h2>{item['title']}</h2>"
        
        if item['type'] == 'text':
            html += f"<p>{item['content']}</p>"
        elif item['type'] == 'table':
            html += item['content']
        elif item['type'] == 'chart':
            html += f'<div class="chart-container">{item["content"]}</div>'
    
    html += f"""
        <div class="footer">
            <p>Report generated by YouTrack Data Extraction & Visualization System</p>
        </div>
    </body>
    </html>
    """
    
    return html
