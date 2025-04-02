"""
Settings page for configuring the YouTrack data extraction and visualization system.
"""
import streamlit as st
import os
import json
from datetime import datetime

from config import youtrack_config, app_config
from utils import check_data_freshness, format_timedelta

# Page config
st.set_page_config(
    page_title="Settings - YouTrack Analytics",
    page_icon="⚙️",
    layout="wide"
)

# Title
st.title("System Settings")
st.markdown("Configure application settings and manage data")

# YouTrack Configuration
st.header("YouTrack Configuration")

youtrack_url = st.text_input("YouTrack URL", value=youtrack_config.base_url)

# Mask token for display
masked_token = youtrack_config.token[:5] + "..." + youtrack_config.token[-5:] if len(youtrack_config.token) > 10 else "..."
token_input = st.text_input("YouTrack API Token", value=masked_token, type="password")

project_id = st.text_input("Project ID", value=youtrack_config.project_id)

col1, col2 = st.columns(2)
with col1:
    max_retries = st.number_input("Max Retries", value=youtrack_config.max_retries, min_value=1, max_value=10)
with col2:
    retry_delay = st.number_input("Retry Delay (seconds)", value=youtrack_config.retry_delay, min_value=1, max_value=60)

# Note about token security
st.info(
    """
    **Security Note**: The YouTrack API token is stored in memory only and not persisted to disk in plain text. 
    For production use, it's recommended to set the token as an environment variable.
    """
)

# Application Settings
st.header("Application Settings")

col1, col2 = st.columns(2)
with col1:
    refresh_interval = st.number_input(
        "Auto-refresh Interval (seconds)",
        value=app_config.refresh_interval,
        min_value=300,
        max_value=86400
    )
with col2:
    page_size = st.number_input(
        "API Page Size",
        value=app_config.page_size,
        min_value=10,
        max_value=100
    )

log_level = st.selectbox(
    "Log Level",
    options=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    index=1  # Default to INFO
)

# Data Management
st.header("Data Management")

# Display data freshness
is_fresh, age_hours = check_data_freshness()
if age_hours is not None:
    st.info(
        f"Data age: {age_hours:.1f} hours " + 
        ("(up to date)" if is_fresh else "(refresh recommended)")
    )
else:
    st.warning("No data files found. Please extract data from YouTrack.")

# Data management actions
col1, col2 = st.columns(2)

with col1:
    if st.button("Clear All Data", type="secondary"):
        try:
            # Clear data files
            issues_file = os.path.join(app_config.data_dir, app_config.issues_file)
            processed_file = os.path.join(app_config.data_dir, app_config.processed_data_file)
            
            if os.path.exists(issues_file):
                os.remove(issues_file)
            
            if os.path.exists(processed_file):
                os.remove(processed_file)
                
            # Reset session state
            if 'data_processor' in st.session_state:
                st.session_state.data_loaded = False
                
            st.success("All data files cleared successfully.")
            st.rerun()
        except Exception as e:
            st.error(f"Error clearing data: {str(e)}")

# Save settings button
if st.button("Save Settings", type="primary"):
    # In a real application, we would update configuration
    # Since this is a demo and we don't want to modify environment variables
    # or write to configuration files, we'll just display a success message
    st.success("Settings saved successfully!")
    st.info(
        """
        **Note**: In this demo, settings are not actually persisted between sessions.
        In a production application, these would be saved to a configuration file or database.
        """
    )

# System Information
st.header("System Information")

# Display directories
st.subheader("Data Directories")
st.json({
    "Data Directory": app_config.data_dir,
    "Reports Directory": app_config.report_output_dir
})

# Display version information
st.subheader("Version Information")
st.markdown(
    """
    **YouTrack Analytics System**
    - Version: 1.0.0
    - Last Updated: 2023-11-29
    """
)

# About section
st.header("About")
st.markdown(
    """
    **YouTrack Data Extraction & Visualization System**
    
    This system provides comprehensive analytics and reporting for YouTrack projects,
    specifically designed for the Mercedes "MQ EIS/KG BSW" project.
    
    Features:
    - Automated data extraction from YouTrack API
    - Interactive dashboards and visualizations
    - Customizable reports
    - Data exploration tools
    """
)
