"""
Dashboard page displaying key project metrics and visualizations.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime, timedelta

from visualizations import (
    create_issues_by_status_chart,
    create_issues_by_assignee_chart,
    create_resolution_time_histogram,
    create_issues_over_time_chart,
    create_sprint_completion_chart,
    create_status_flow_sankey
)

# Page config
st.set_page_config(
    page_title="Dashboard - YouTrack Analytics",
    page_icon="📊",
    layout="wide"
)

# Title
st.title("Project Dashboard")
st.markdown("Overview of key metrics and visualizations for the project")

# Check if data is loaded
if 'data_processor' not in st.session_state or not st.session_state.data_loaded:
    st.warning("No data loaded. Please go to the main page and click 'Refresh Data'.")
    st.stop()

# Get data processor
data_processor = st.session_state.data_processor

# Create dashboard layout
col1, col2 = st.columns(2)

# Issue Status Distribution
with col1:
    st.subheader("Issue Status Distribution")
    
    # Get status data
    status_field = data_processor.custom_fields_df[data_processor.custom_fields_df['field_name'] == 'State']
    
    if not status_field.empty:
        status_chart = create_issues_by_status_chart(status_field)
        st.plotly_chart(status_chart, use_container_width=True)
    else:
        st.info("No status data available.")

# Assignee Workload
with col2:
    st.subheader("Assignee Workload")
    
    # Get assignee workload data
    assignee_workload = data_processor.get_assignee_workload()
    
    if not assignee_workload.empty:
        assignee_chart = create_issues_by_assignee_chart(assignee_workload)
        st.plotly_chart(assignee_chart, use_container_width=True)
    else:
        st.info("No assignee data available.")

# Issues Over Time
st.subheader("Issues Over Time")
issues_time_chart = create_issues_over_time_chart(data_processor.issues_df)
st.plotly_chart(issues_time_chart, use_container_width=True)

# Issue Resolution Times
col1, col2 = st.columns(2)

with col1:
    st.subheader("Issue Resolution Times")
    resolution_times = data_processor.get_issue_resolution_times()
    
    if not resolution_times.empty:
        resolution_chart = create_resolution_time_histogram(resolution_times)
        st.plotly_chart(resolution_chart, use_container_width=True)
        
        # Show average and median resolution times
        avg_time = resolution_times['resolution_days'].mean()
        median_time = resolution_times['resolution_days'].median()
        
        st.metric("Average Resolution Time", f"{avg_time:.1f} days")
        st.metric("Median Resolution Time", f"{median_time:.1f} days")
    else:
        st.info("No resolved issues found for time analysis.")

# Sprint Completion Rates
with col2:
    st.subheader("Sprint Completion Rates")
    sprint_stats = data_processor.get_sprint_statistics()
    
    if sprint_stats:
        sprint_chart = create_sprint_completion_chart(sprint_stats)
        st.plotly_chart(sprint_chart, use_container_width=True)
    else:
        st.info("No sprint data available.")

# Status Flow Diagram
st.subheader("Issue Status Flow")
status_changes = data_processor.get_status_transitions()

if not status_changes.empty:
    status_flow = create_status_flow_sankey(status_changes)
    st.plotly_chart(status_flow, use_container_width=True)
else:
    st.info("No status transition data available.")

# Recent activity
st.subheader("Recent Activity")

# Get recent status changes
if not data_processor.history_df.empty:
    # Filter for recent activity (last 7 days)
    recent_cutoff = pd.Timestamp.now() - pd.Timedelta(days=7)
    recent_activity = data_processor.history_df[data_processor.history_df['timestamp'] > recent_cutoff].copy()
    
    if not recent_activity.empty:
        # Sort by timestamp (most recent first)
        recent_activity = recent_activity.sort_values('timestamp', ascending=False)
        
        # Add issue summary
        recent_activity = recent_activity.merge(
            data_processor.issues_df[['id', 'summary']],
            left_on='issue_id',
            right_on='id',
            how='left'
        )
        
        # Format for display
        display_activity = recent_activity[['timestamp', 'issue_id', 'summary', 'field_name', 'removed', 'added', 'author']].head(10)
        display_activity['timestamp'] = display_activity['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
        
        # Rename columns for better display
        display_activity.columns = ['Time', 'Issue ID', 'Summary', 'Field', 'Old Value', 'New Value', 'Author']
        
        st.dataframe(display_activity, use_container_width=True)
    else:
        st.info("No recent activity in the last 7 days.")
else:
    st.info("No activity history data available.")
