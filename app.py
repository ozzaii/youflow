"""
Main application entry point for the YouTrack data extraction and visualization system.
"""
import streamlit as st
import os
import json
import logging
import pandas as pd
from datetime import datetime

from youtrack_api import YouTrackAPI
from data_processor import DataProcessor
from ai_insights import AIInsightsGenerator
from utils import check_data_freshness, format_timedelta
from config import youtrack_config, app_config

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="YouTrack Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state for data
if 'data_processor' not in st.session_state:
    st.session_state.data_processor = DataProcessor()

if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False

if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = None
    
# Initialize AI insights generator
if 'ai_insights_generator' not in st.session_state:
    st.session_state.ai_insights_generator = AIInsightsGenerator()
    
# Cache for AI-generated insights
if 'daily_insights' not in st.session_state:
    st.session_state.daily_insights = None
    
if 'trend_analysis' not in st.session_state:
    st.session_state.trend_analysis = None
    
if 'followup_questions' not in st.session_state:
    st.session_state.followup_questions = None

def load_or_refresh_data():
    """Load data from files or refresh from API if needed."""
    is_fresh, age_hours = check_data_freshness()
    
    # Initialize YouTrack API and data processor
    youtrack_api = YouTrackAPI()
    data_processor = st.session_state.data_processor
    
    if not is_fresh:
        with st.spinner("Extracting data from YouTrack API..."):
            try:
                # Extract data from YouTrack
                youtrack_api.extract_full_project_data()
                st.success("Data extracted successfully!")
            except Exception as e:
                st.error(f"Error extracting data: {str(e)}")
                logger.error(f"Error extracting data: {str(e)}", exc_info=True)
                return False
    
    # Process the data
    with st.spinner("Processing data..."):
        if data_processor.load_data():
            if data_processor.process_data():
                st.session_state.data_loaded = True
                st.session_state.last_refresh = datetime.now()
                return True
    
    return False

def display_project_info():
    """Display basic project information."""
    data_processor = st.session_state.data_processor
    
    # Get project name
    project_name = youtrack_config.project_id
    
    # Calculate some basic stats
    total_issues = len(data_processor.issues_df) if data_processor.issues_df is not None else 0
    open_issues = data_processor.issues_df[data_processor.issues_df['resolved'].isna()].shape[0] if data_processor.issues_df is not None else 0
    resolved_issues = total_issues - open_issues
    
    # Status information
    if data_processor.custom_fields_df is not None:
        status_field = data_processor.custom_fields_df[data_processor.custom_fields_df['field_name'] == 'State']
        status_count = status_field['field_value'].value_counts().to_dict()
    else:
        status_count = {}
    
    # Display information
    st.title(f"YouTrack Project: {project_name}")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Issues", total_issues)
    
    with col2:
        st.metric("Open Issues", open_issues)
    
    with col3:
        st.metric("Resolved Issues", resolved_issues)
    
    # Display status breakdown
    if status_count:
        st.subheader("Issue Status Breakdown")
        status_df = pd.DataFrame({
            'Status': list(status_count.keys()),
            'Count': list(status_count.values())
        }).sort_values('Count', ascending=False)
        
        st.dataframe(status_df, use_container_width=True)

def display_data_freshness():
    """Display information about data freshness."""
    if st.session_state.last_refresh:
        time_since_refresh = datetime.now() - st.session_state.last_refresh
        st.sidebar.info(
            f"Data last refreshed: {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')} "
            f"({format_timedelta(time_since_refresh)} ago)"
        )
    else:
        is_fresh, age_hours = check_data_freshness()
        if age_hours:
            st.sidebar.info(f"Data age: {age_hours:.1f} hours")
        else:
            st.sidebar.warning("No data available. Please refresh data.")
            
def generate_ai_insights():
    """Generate AI-powered insights from the data."""
    data_processor = st.session_state.data_processor
    ai_generator = st.session_state.ai_insights_generator
    
    # Daily report
    if st.session_state.daily_insights is None:
        with st.spinner("Generating AI insights..."):
            st.session_state.daily_insights = ai_generator.generate_daily_report(data_processor)
    
    # Trend analysis
    if st.session_state.trend_analysis is None:
        with st.spinner("Analyzing issue trends..."):
            st.session_state.trend_analysis = ai_generator.analyze_issue_trends(data_processor)
    
    # Follow-up questions
    if st.session_state.followup_questions is None:
        with st.spinner("Generating follow-up questions..."):
            st.session_state.followup_questions = ai_generator.generate_followup_questions(data_processor)

def display_ai_insights():
    """Display AI-powered insights."""
    st.header("🧠 AI-Powered Insights", divider=True)
    
    # Check if we have insights yet
    if st.session_state.daily_insights is None:
        st.info("AI insights are being generated... This may take a moment.")
        return
        
    if "error" in st.session_state.daily_insights:
        st.error(st.session_state.daily_insights["error"])
        return
    
    # Executive Summary
    if "executive_summary" in st.session_state.daily_insights:
        st.subheader("Executive Summary")
        st.write(st.session_state.daily_insights["executive_summary"])
    
    # Show the sections in expandable sections
    with st.expander("Key Metrics", expanded=False):
        if "key_metrics" in st.session_state.daily_insights:
            st.markdown(st.session_state.daily_insights["key_metrics"])
        else:
            st.info("No key metrics analysis available.")
    
    with st.expander("Risks & Bottlenecks", expanded=False):
        if "risks_bottlenecks" in st.session_state.daily_insights:
            st.markdown(st.session_state.daily_insights["risks_bottlenecks"])
        else:
            st.info("No risks analysis available.")
    
    with st.expander("Recommendations", expanded=False):
        if "recommendations" in st.session_state.daily_insights:
            st.markdown(st.session_state.daily_insights["recommendations"])
        else:
            st.info("No recommendations available.")
    
    with st.expander("Team Performance", expanded=False):
        if "team_performance" in st.session_state.daily_insights:
            st.markdown(st.session_state.daily_insights["team_performance"])
        else:
            st.info("No team performance analysis available.")
    
    # Follow-up questions
    if st.session_state.followup_questions and len(st.session_state.followup_questions) > 0:
        st.subheader("Follow-up Questions")
        for question in st.session_state.followup_questions:
            st.markdown(f"• {question}")
    
    # Add a refresh button
    if st.button("Regenerate AI Insights"):
        st.session_state.daily_insights = None
        st.session_state.trend_analysis = None
        st.session_state.followup_questions = None
        generate_ai_insights()
        st.rerun()

def main():
    """Main application function."""
    # Sidebar
    st.sidebar.title("YouTrack Analytics")
    st.sidebar.markdown("---")
    
    # Add refresh button in sidebar
    if st.sidebar.button("Refresh Data"):
        with st.spinner("Refreshing data..."):
            if load_or_refresh_data():
                st.sidebar.success("Data refreshed successfully!")
            else:
                st.sidebar.error("Error refreshing data. Check logs for details.")
    
    # Display data freshness info
    display_data_freshness()
    
    # Add navigation (handled by Streamlit pages automatically)
    st.sidebar.markdown("---")
    st.sidebar.markdown("## Navigation")
    st.sidebar.markdown("Use the menu above to navigate between pages.")
    
    # Main content
    if not st.session_state.data_loaded:
        # First load - try to load data from files
        data_processor = st.session_state.data_processor
        if data_processor.load_processed_data():
            st.session_state.data_loaded = True
            st.session_state.last_refresh = datetime.fromtimestamp(
                os.path.getmtime(os.path.join(app_config.data_dir, app_config.processed_data_file))
            )
    
    if st.session_state.data_loaded:
        # Display project information
        display_project_info()
        
        # Generate AI insights if needed
        if (st.session_state.daily_insights is None or 
            st.session_state.trend_analysis is None or 
            st.session_state.followup_questions is None):
            generate_ai_insights()
        
        # Display AI insights
        display_ai_insights()
        
        st.markdown("---")
        st.markdown(
            """
            ## YouTrack Data Extraction & Visualization System
            
            Welcome to the YouTrack Analytics Dashboard for the Mercedes "MQ EIS/KG BSW" project.
            Use the navigation menu to explore different reports and visualizations.
            
            ### Available Features:
            
            - **Dashboard:** Overview of project metrics and status
            - **Reports:** Generate and export standardized reports
            - **Data Explorer:** Explore the raw data and custom queries
            - **Settings:** Configure system settings
            - **AI Insights:** AI-powered analysis and recommendations
            
            Use the "Refresh Data" button in the sidebar to fetch the latest data from YouTrack.
            """
        )
    else:
        st.warning("No data loaded. Please click 'Refresh Data' to fetch data from YouTrack.")
        
        st.markdown(
            """
            ## Welcome to YouTrack Analytics!
            
            This system provides comprehensive analytics and reporting for YouTrack projects,
            specifically designed for the Mercedes "MQ EIS/KG BSW" project.
            
            To get started:
            1. Click the "Refresh Data" button in the sidebar
            2. Wait for the data to be extracted and processed
            3. Explore the dashboard and reports
            
            Initial data extraction may take a few minutes depending on the size of your project.
            """
        )

if __name__ == "__main__":
    main()
