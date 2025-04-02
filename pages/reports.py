"""
Reports page for generating standardized reports from YouTrack data.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os

from utils import (
    generate_report_filename,
    save_report,
    create_html_report,
    format_timedelta
)
from visualizations import (
    create_issues_by_status_chart,
    create_resolution_time_histogram,
    create_issues_over_time_chart,
    create_sprint_completion_chart
)

# Page config
st.set_page_config(
    page_title="Reports - YouTrack Analytics",
    page_icon="📄",
    layout="wide"
)

# Title
st.title("Project Reports")
st.markdown("Generate and download standardized reports for the project")

# Check if data is loaded
if 'data_processor' not in st.session_state or not st.session_state.data_loaded:
    st.warning("No data loaded. Please go to the main page and click 'Refresh Data'.")
    st.stop()

# Get data processor
data_processor = st.session_state.data_processor

# Define report types
REPORT_TYPES = {
    "project_overview": "Project Overview",
    "sprint_report": "Sprint Performance Report",
    "issue_resolution": "Issue Resolution Analysis",
    "assignee_workload": "Assignee Workload Report"
}

# Sidebar for report configuration
st.sidebar.header("Report Configuration")

# Select report type
report_type = st.sidebar.selectbox(
    "Report Type",
    options=list(REPORT_TYPES.keys()),
    format_func=lambda x: REPORT_TYPES[x]
)

# Report date range
st.sidebar.subheader("Date Range")
date_start = st.sidebar.date_input(
    "Start Date",
    value=datetime.now() - timedelta(days=30)
)
date_end = st.sidebar.date_input(
    "End Date",
    value=datetime.now()
)

# Additional options based on report type
if report_type == "sprint_report":
    # Get available sprints
    available_sprints = []
    if data_processor.sprint_df is not None and not data_processor.sprint_df.empty:
        available_sprints = data_processor.sprint_df['sprint_name'].unique().tolist()
    
    selected_sprint = st.sidebar.selectbox(
        "Select Sprint",
        options=available_sprints if available_sprints else ["No sprints available"]
    )

elif report_type == "assignee_workload":
    # Get available assignees
    available_assignees = []
    if data_processor.issues_df is not None and not data_processor.issues_df.empty:
        available_assignees = data_processor.issues_df['assignee'].dropna().unique().tolist()
    
    selected_assignees = st.sidebar.multiselect(
        "Select Assignees",
        options=available_assignees,
        default=available_assignees[:5] if len(available_assignees) > 0 else []
    )

# Report format
report_format = st.sidebar.selectbox(
    "Report Format",
    options=["HTML", "PDF"],
    index=0
)

# Generate button
generate_report = st.sidebar.button("Generate Report", type="primary")

# Function to generate project overview report
def generate_project_overview():
    """Generate project overview report."""
    # Filter data by date range
    date_start_ts = pd.Timestamp(date_start)
    date_end_ts = pd.Timestamp(date_end)
    
    filtered_issues = data_processor.issues_df[
        (data_processor.issues_df['created'] >= date_start_ts) & 
        (data_processor.issues_df['created'] <= date_end_ts)
    ]
    
    # Get status data
    status_field = data_processor.custom_fields_df[
        data_processor.custom_fields_df['field_name'] == 'State'
    ]
    status_field = status_field[status_field['issue_id'].isin(filtered_issues['id'])]
    
    # Calculate statistics
    total_issues = len(filtered_issues)
    open_issues = filtered_issues[filtered_issues['resolved'].isna()].shape[0]
    resolved_issues = total_issues - open_issues
    
    # Get sprint stats
    sprint_stats = data_processor.get_sprint_statistics()
    
    # Create charts
    status_chart = create_issues_by_status_chart(status_field)
    issues_time_chart = create_issues_over_time_chart(filtered_issues)
    
    # Display report preview
    st.header("Project Overview Report")
    st.subheader(f"Period: {date_start} to {date_end}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Issues", total_issues)
    col2.metric("Open Issues", open_issues)
    col3.metric("Resolved Issues", resolved_issues)
    
    st.plotly_chart(status_chart, use_container_width=True)
    st.plotly_chart(issues_time_chart, use_container_width=True)
    
    # Prepare content for HTML report
    content = [
        {
            "type": "text",
            "title": "Report Summary",
            "content": f"""
            This report provides an overview of project activity from {date_start} to {date_end}.
            <br><br>
            <b>Key Statistics:</b><br>
            Total Issues: {total_issues}<br>
            Open Issues: {open_issues}<br>
            Resolved Issues: {resolved_issues}<br>
            """
        },
        {
            "type": "chart",
            "title": "Issue Status Distribution",
            "content": status_chart.to_html(full_html=False, include_plotlyjs='cdn')
        },
        {
            "type": "chart",
            "title": "Issues Over Time",
            "content": issues_time_chart.to_html(full_html=False, include_plotlyjs='cdn')
        }
    ]
    
    # Add recent activity table
    if not data_processor.history_df.empty:
        recent_cutoff = pd.Timestamp(date_start_ts)
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
            display_activity = recent_activity[['timestamp', 'issue_id', 'summary', 'field_name', 'removed', 'added', 'author']].head(20)
            display_activity['timestamp'] = display_activity['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            
            # Rename columns for better display
            display_activity.columns = ['Time', 'Issue ID', 'Summary', 'Field', 'Old Value', 'New Value', 'Author']
            
            # Convert to HTML table
            activity_html = display_activity.to_html(index=False, classes="table table-striped")
            
            content.append({
                "type": "table",
                "title": "Recent Activity",
                "content": activity_html
            })
    
    # Return the report HTML
    return create_html_report("Project Overview Report", content)

# Function to generate sprint report
def generate_sprint_report():
    """Generate sprint performance report."""
    if 'selected_sprint' not in locals() or selected_sprint == "No sprints available":
        st.error("No sprint data available for reporting.")
        return None
    
    # Get issues in the selected sprint
    sprint_issues = data_processor.sprint_df[data_processor.sprint_df['sprint_name'] == selected_sprint]['issue_id'].tolist()
    
    # Get issue details
    sprint_issue_details = data_processor.issues_df[data_processor.issues_df['id'].isin(sprint_issues)].copy()
    
    # Calculate statistics
    total_issues = len(sprint_issues)
    resolved_issues = sprint_issue_details.dropna(subset=['resolved']).shape[0]
    completion_rate = resolved_issues / total_issues if total_issues > 0 else 0
    
    # Get status breakdown
    status_field = data_processor.custom_fields_df[
        (data_processor.custom_fields_df['field_name'] == 'State') & 
        (data_processor.custom_fields_df['issue_id'].isin(sprint_issues))
    ]
    
    # Display report preview
    st.header(f"Sprint Report: {selected_sprint}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Issues", total_issues)
    col2.metric("Completed Issues", resolved_issues)
    col3.metric("Completion Rate", f"{completion_rate:.1%}")
    
    # Create status chart
    if not status_field.empty:
        status_chart = create_issues_by_status_chart(status_field)
        st.plotly_chart(status_chart, use_container_width=True)
    
    # Show issue list
    st.subheader("Sprint Issues")
    if not sprint_issue_details.empty:
        # Add status column
        sprint_issue_details['status'] = sprint_issue_details['id'].apply(
            lambda x: data_processor.custom_fields_df[
                (data_processor.custom_fields_df['issue_id'] == x) & 
                (data_processor.custom_fields_df['field_name'] == 'State')
            ]['field_value'].values[0] if len(data_processor.custom_fields_df[
                (data_processor.custom_fields_df['issue_id'] == x) & 
                (data_processor.custom_fields_df['field_name'] == 'State')
            ]) > 0 else ''
        )
        
        # Display issues
        display_issues = sprint_issue_details[['id', 'summary', 'status', 'assignee', 'created', 'resolved']]
        display_issues['created'] = display_issues['created'].dt.strftime('%Y-%m-%d')
        display_issues['resolved'] = display_issues['resolved'].dt.strftime('%Y-%m-%d')
        
        st.dataframe(display_issues, use_container_width=True)
    
    # Prepare content for HTML report
    content = [
        {
            "type": "text",
            "title": "Sprint Summary",
            "content": f"""
            This report provides an analysis of the sprint: <b>{selected_sprint}</b>
            <br><br>
            <b>Key Statistics:</b><br>
            Total Issues: {total_issues}<br>
            Completed Issues: {resolved_issues}<br>
            Completion Rate: {completion_rate:.1%}<br>
            """
        }
    ]
    
    # Add status chart
    if not status_field.empty:
        content.append({
            "type": "chart",
            "title": "Issue Status Distribution",
            "content": status_chart.to_html(full_html=False, include_plotlyjs='cdn')
        })
    
    # Add issue table
    if not sprint_issue_details.empty:
        # Format for HTML
        display_issues = sprint_issue_details[['id', 'summary', 'status', 'assignee', 'created', 'resolved']]
        display_issues['created'] = display_issues['created'].dt.strftime('%Y-%m-%d')
        display_issues['resolved'] = display_issues['resolved'].dt.strftime('%Y-%m-%d')
        display_issues.columns = ['ID', 'Summary', 'Status', 'Assignee', 'Created', 'Resolved']
        
        # Convert to HTML table
        issues_html = display_issues.to_html(index=False, classes="table table-striped")
        
        content.append({
            "type": "table",
            "title": "Sprint Issues",
            "content": issues_html
        })
    
    # Return the report HTML
    return create_html_report(f"Sprint Report: {selected_sprint}", content)

# Function to generate issue resolution report
def generate_issue_resolution_report():
    """Generate issue resolution analysis report."""
    # Filter data by date range
    date_start_ts = pd.Timestamp(date_start)
    date_end_ts = pd.Timestamp(date_end)
    
    resolved_issues = data_processor.issues_df[
        (data_processor.issues_df['resolved'] >= date_start_ts) & 
        (data_processor.issues_df['resolved'] <= date_end_ts)
    ].copy()
    
    # Calculate resolution time
    if not resolved_issues.empty:
        resolved_issues['resolution_time'] = resolved_issues['resolved'] - resolved_issues['created']
        resolved_issues['resolution_days'] = resolved_issues['resolution_time'].dt.total_seconds() / (24 * 3600)
        
        # Calculate statistics
        total_resolved = len(resolved_issues)
        avg_resolution = resolved_issues['resolution_days'].mean()
        median_resolution = resolved_issues['resolution_days'].median()
        
        # Create histogram
        resolution_chart = create_resolution_time_histogram(resolved_issues)
        
        # Display report preview
        st.header("Issue Resolution Analysis")
        st.subheader(f"Period: {date_start} to {date_end}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Issues Resolved", total_resolved)
        col2.metric("Average Resolution Time", f"{avg_resolution:.1f} days")
        col3.metric("Median Resolution Time", f"{median_resolution:.1f} days")
        
        st.plotly_chart(resolution_chart, use_container_width=True)
        
        # Breakdown by assignee
        st.subheader("Resolution Time by Assignee")
        assignee_resolution = resolved_issues.groupby('assignee')['resolution_days'].agg(['count', 'mean', 'median']).reset_index()
        assignee_resolution.columns = ['Assignee', 'Issues Resolved', 'Avg Days', 'Median Days']
        assignee_resolution = assignee_resolution.sort_values('Issues Resolved', ascending=False)
        
        st.dataframe(assignee_resolution, use_container_width=True)
        
        # Show the resolved issues
        st.subheader("Recently Resolved Issues")
        display_resolved = resolved_issues.sort_values('resolved', ascending=False)[
            ['id', 'summary', 'assignee', 'created', 'resolved', 'resolution_days']
        ].head(20)
        
        display_resolved['created'] = display_resolved['created'].dt.strftime('%Y-%m-%d')
        display_resolved['resolved'] = display_resolved['resolved'].dt.strftime('%Y-%m-%d')
        display_resolved['resolution_days'] = display_resolved['resolution_days'].round(1)
        
        st.dataframe(display_resolved, use_container_width=True)
        
        # Prepare content for HTML report
        content = [
            {
                "type": "text",
                "title": "Issue Resolution Summary",
                "content": f"""
                This report analyzes issue resolution from {date_start} to {date_end}.
                <br><br>
                <b>Key Statistics:</b><br>
                Issues Resolved: {total_resolved}<br>
                Average Resolution Time: {avg_resolution:.1f} days<br>
                Median Resolution Time: {median_resolution:.1f} days<br>
                """
            },
            {
                "type": "chart",
                "title": "Resolution Time Distribution",
                "content": resolution_chart.to_html(full_html=False, include_plotlyjs='cdn')
            }
        ]
        
        # Add assignee breakdown
        assignee_html = assignee_resolution.to_html(index=False, classes="table table-striped")
        content.append({
            "type": "table",
            "title": "Resolution Time by Assignee",
            "content": assignee_html
        })
        
        # Add resolved issues
        display_resolved.columns = ['ID', 'Summary', 'Assignee', 'Created', 'Resolved', 'Days to Resolve']
        resolved_html = display_resolved.to_html(index=False, classes="table table-striped")
        content.append({
            "type": "table",
            "title": "Recently Resolved Issues",
            "content": resolved_html
        })
        
        # Return the report HTML
        return create_html_report("Issue Resolution Analysis", content)
    else:
        st.error("No issues were resolved in the selected date range.")
        return None

# Function to generate assignee workload report
def generate_assignee_workload_report():
    """Generate assignee workload report."""
    if 'selected_assignees' not in locals() or not selected_assignees:
        st.error("No assignees selected for reporting.")
        return None
    
    # Filter for selected assignees
    assignee_issues = data_processor.issues_df[
        data_processor.issues_df['assignee'].isin(selected_assignees)
    ].copy()
    
    # Get open issues
    open_issues = assignee_issues[assignee_issues['resolved'].isna()].copy()
    
    # Get workload by assignee
    workload = data_processor.get_assignee_workload()
    workload = workload[workload['assignee'].isin(selected_assignees)]
    
    # Display report preview
    st.header("Assignee Workload Report")
    
    # Create workload chart
    if not workload.empty:
        workload_chart = create_issues_by_assignee_chart(workload)
        st.plotly_chart(workload_chart, use_container_width=True)
    
    # Show open issues by assignee
    for assignee in selected_assignees:
        st.subheader(f"Open Issues: {assignee}")
        
        assignee_open = open_issues[open_issues['assignee'] == assignee]
        
        if not assignee_open.empty:
            # Get status for each issue
            assignee_open['status'] = assignee_open['id'].apply(
                lambda x: data_processor.custom_fields_df[
                    (data_processor.custom_fields_df['issue_id'] == x) & 
                    (data_processor.custom_fields_df['field_name'] == 'State')
                ]['field_value'].values[0] if len(data_processor.custom_fields_df[
                    (data_processor.custom_fields_df['issue_id'] == x) & 
                    (data_processor.custom_fields_df['field_name'] == 'State')
                ]) > 0 else ''
            )
            
            # Display issues
            display_issues = assignee_open[['id', 'summary', 'status', 'created']]
            display_issues['created'] = display_issues['created'].dt.strftime('%Y-%m-%d')
            
            st.dataframe(display_issues, use_container_width=True)
        else:
            st.info(f"No open issues for {assignee}")
    
    # Prepare content for HTML report
    content = [
        {
            "type": "text",
            "title": "Assignee Workload Summary",
            "content": f"""
            This report analyzes the current workload for selected assignees.
            <br><br>
            <b>Selected Assignees:</b><br>
            {', '.join(selected_assignees)}<br>
            """
        }
    ]
    
    # Add workload chart
    if not workload.empty:
        content.append({
            "type": "chart",
            "title": "Current Workload by Assignee",
            "content": workload_chart.to_html(full_html=False, include_plotlyjs='cdn')
        })
    
    # Add open issues for each assignee
    for assignee in selected_assignees:
        assignee_open = open_issues[open_issues['assignee'] == assignee]
        
        if not assignee_open.empty:
            # Get status for each issue
            assignee_open['status'] = assignee_open['id'].apply(
                lambda x: data_processor.custom_fields_df[
                    (data_processor.custom_fields_df['issue_id'] == x) & 
                    (data_processor.custom_fields_df['field_name'] == 'State')
                ]['field_value'].values[0] if len(data_processor.custom_fields_df[
                    (data_processor.custom_fields_df['issue_id'] == x) & 
                    (data_processor.custom_fields_df['field_name'] == 'State')
                ]) > 0 else ''
            )
            
            # Format for HTML
            display_issues = assignee_open[['id', 'summary', 'status', 'created']]
            display_issues['created'] = display_issues['created'].dt.strftime('%Y-%m-%d')
            display_issues.columns = ['ID', 'Summary', 'Status', 'Created']
            
            # Convert to HTML table
            issues_html = display_issues.to_html(index=False, classes="table table-striped")
            
            content.append({
                "type": "table",
                "title": f"Open Issues: {assignee} ({len(assignee_open)} issues)",
                "content": issues_html
            })
    
    # Return the report HTML
    return create_html_report("Assignee Workload Report", content)

# Handle report generation
if generate_report:
    report_html = None
    
    if report_type == "project_overview":
        report_html = generate_project_overview()
    elif report_type == "sprint_report":
        report_html = generate_sprint_report()
    elif report_type == "issue_resolution":
        report_html = generate_issue_resolution_report()
    elif report_type == "assignee_workload":
        report_html = generate_assignee_workload_report()
    
    if report_html:
        # Save the report
        report_filename = generate_report_filename(report_type, format="html")
        report_path = save_report(report_html, report_filename)
        
        # Provide download link
        with open(report_path, "rb") as file:
            st.download_button(
                label="Download Report",
                data=file,
                file_name=report_filename,
                mime="text/html"
            )
        
        st.success(f"Report generated successfully: {report_filename}")
else:
    # Show report type description
    if report_type == "project_overview":
        st.info(
            """
            **Project Overview Report**
            
            This report provides a comprehensive overview of the project's status, including:
            - Issue status distribution
            - Issue creation and resolution trends
            - Recent activity
            - Key performance metrics
            
            Use the date range selector to focus on a specific time period.
            """
        )
    elif report_type == "sprint_report":
        st.info(
            """
            **Sprint Performance Report**
            
            This report analyzes the performance of a specific sprint, including:
            - Completion rate
            - Issue status breakdown
            - List of issues and their status
            - Sprint timeline
            
            Select a sprint from the dropdown to generate the report.
            """
        )
    elif report_type == "issue_resolution":
        st.info(
            """
            **Issue Resolution Analysis**
            
            This report focuses on issue resolution metrics, including:
            - Resolution time statistics
            - Resolution time distribution
            - Assignee resolution performance
            - Recently resolved issues
            
            Use the date range selector to focus on issues resolved in a specific period.
            """
        )
    elif report_type == "assignee_workload":
        st.info(
            """
            **Assignee Workload Report**
            
            This report analyzes the current workload for selected assignees, including:
            - Number of open issues per assignee
            - Breakdown of issues by status
            - Detailed list of open issues
            
            Select one or more assignees to include in the report.
            """
        )
