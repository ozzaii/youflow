"""
Module for creating visualizations from the processed YouTrack data.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np

def create_issues_by_status_chart(df: pd.DataFrame, status_field: str = 'field_value') -> go.Figure:
    """
    Create a pie chart showing distribution of issues by status.
    
    Args:
        df: DataFrame containing issue status information
        status_field: Column name that contains status values
        
    Returns:
        Plotly figure object
    """
    status_counts = df[status_field].value_counts().reset_index()
    status_counts.columns = ['Status', 'Count']
    
    fig = px.pie(
        status_counts, 
        values='Count', 
        names='Status',
        title='Issues by Status',
        color_discrete_sequence=px.colors.qualitative.Safe
    )
    
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(
        legend_title_text='Status',
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5)
    )
    
    return fig

def create_issues_by_assignee_chart(df: pd.DataFrame) -> go.Figure:
    """
    Create a horizontal bar chart showing issues by assignee.
    
    Args:
        df: DataFrame with 'assignee' and issue count columns
        
    Returns:
        Plotly figure object
    """
    if df.empty:
        # Create empty figure if no data
        fig = go.Figure()
        fig.update_layout(title='No assignee data available')
        return fig
    
    # Sort by issue count descending
    df_sorted = df.sort_values('open_issues', ascending=True)
    
    fig = px.bar(
        df_sorted,
        y='assignee',
        x='open_issues',
        orientation='h',
        title='Open Issues by Assignee',
        labels={'assignee': 'Assignee', 'open_issues': 'Number of Open Issues'},
        color='open_issues',
        color_continuous_scale=px.colors.sequential.Viridis
    )
    
    fig.update_layout(
        xaxis_title='Number of Open Issues',
        yaxis_title='Assignee',
        coloraxis_showscale=False
    )
    
    return fig

def create_resolution_time_histogram(df: pd.DataFrame) -> go.Figure:
    """
    Create a histogram of issue resolution times.
    
    Args:
        df: DataFrame with resolution time information
        
    Returns:
        Plotly figure object
    """
    fig = px.histogram(
        df,
        x='resolution_days',
        nbins=20,
        title='Distribution of Issue Resolution Times',
        labels={'resolution_days': 'Resolution Time (days)'},
        color_discrete_sequence=['#3366CC']
    )
    
    fig.update_layout(
        xaxis_title='Resolution Time (days)',
        yaxis_title='Number of Issues',
        bargap=0.1
    )
    
    # Add median line
    median_val = df['resolution_days'].median()
    fig.add_vline(
        x=median_val,
        line_dash="dash",
        line_color="red",
        annotation_text=f"Median: {median_val:.1f} days",
        annotation_position="top right"
    )
    
    return fig

def create_issues_over_time_chart(df: pd.DataFrame) -> go.Figure:
    """
    Create a line chart showing issues created and resolved over time.
    
    Args:
        df: DataFrame with 'created' and 'resolved' timestamps
        
    Returns:
        Plotly figure object
    """
    # Calculate weekly created issues
    df['created_week'] = df['created'].dt.to_period('W').dt.start_time
    created_weekly = df.groupby('created_week').size().reset_index()
    created_weekly.columns = ['week', 'created_count']
    
    # Calculate weekly resolved issues
    df_resolved = df.dropna(subset=['resolved'])
    df_resolved['resolved_week'] = df_resolved['resolved'].dt.to_period('W').dt.start_time
    resolved_weekly = df_resolved.groupby('resolved_week').size().reset_index()
    resolved_weekly.columns = ['week', 'resolved_count']
    
    # Merge the data
    weekly_data = created_weekly.merge(resolved_weekly, left_on='week', right_on='week', how='outer').fillna(0)
    weekly_data = weekly_data.sort_values('week')
    
    # Calculate backlog (cumulative difference between created and resolved)
    weekly_data['backlog'] = (weekly_data['created_count'] - weekly_data['resolved_count']).cumsum()
    
    # Create the figure
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=weekly_data['week'],
        y=weekly_data['created_count'],
        mode='lines+markers',
        name='Created',
        line=dict(color='#3366CC', width=2)
    ))
    
    fig.add_trace(go.Scatter(
        x=weekly_data['week'],
        y=weekly_data['resolved_count'],
        mode='lines+markers',
        name='Resolved',
        line=dict(color='#33AA33', width=2)
    ))
    
    fig.add_trace(go.Scatter(
        x=weekly_data['week'],
        y=weekly_data['backlog'],
        mode='lines',
        name='Backlog',
        line=dict(color='#CC6677', width=3)
    ))
    
    fig.update_layout(
        title='Issues Created and Resolved Over Time',
        xaxis_title='Week',
        yaxis_title='Number of Issues',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    
    return fig

def create_sprint_completion_chart(sprint_stats: Dict[str, Dict[str, Any]]) -> go.Figure:
    """
    Create a bar chart showing sprint completion rates.
    
    Args:
        sprint_stats: Dictionary with sprint statistics
        
    Returns:
        Plotly figure object
    """
    sprints = []
    completion_rates = []
    
    for sprint, stats in sprint_stats.items():
        sprints.append(sprint)
        completion_rates.append(stats['completion_rate'] * 100)  # Convert to percentage
    
    # Create DataFrame
    sprint_df = pd.DataFrame({
        'Sprint': sprints,
        'Completion Rate (%)': completion_rates
    })
    
    # Sort by sprint name (assuming they have a numeric or chronological order)
    sprint_df = sprint_df.sort_values('Sprint')
    
    fig = px.bar(
        sprint_df,
        x='Sprint',
        y='Completion Rate (%)',
        title='Sprint Completion Rates',
        color='Completion Rate (%)',
        color_continuous_scale=px.colors.sequential.RdBu
    )
    
    fig.update_layout(
        xaxis_title='Sprint',
        yaxis_title='Completion Rate (%)',
        yaxis=dict(range=[0, 100])
    )
    
    # Add a target line at 100%
    fig.add_hline(
        y=100,
        line_dash="dash",
        line_color="green",
        annotation_text="Target",
        annotation_position="top right"
    )
    
    return fig

def create_status_flow_sankey(status_changes: pd.DataFrame) -> go.Figure:
    """
    Create a Sankey diagram showing the flow of issues between statuses.
    
    Args:
        status_changes: DataFrame with status change information
        
    Returns:
        Plotly figure object
    """
    # If no data, return empty figure
    if status_changes.empty:
        fig = go.Figure()
        fig.update_layout(title='No status transition data available')
        return fig
    
    # Create pairs of from_status -> to_status
    flow_data = []
    for _, row in status_changes.iterrows():
        if pd.notna(row['removed']) and pd.notna(row['added']):
            flow_data.append((row['removed'], row['added']))
    
    # Count occurrences of each transition
    flow_counts = pd.Series(flow_data).value_counts().reset_index()
    flow_counts.columns = ['transition', 'count']
    
    # Extract from and to statuses
    flow_counts['from_status'] = flow_counts['transition'].apply(lambda x: x[0])
    flow_counts['to_status'] = flow_counts['transition'].apply(lambda x: x[1])
    
    # Get unique statuses for node labels
    all_statuses = pd.concat([
        pd.Series(flow_counts['from_status'].unique()),
        pd.Series(flow_counts['to_status'].unique())
    ]).unique()
    
    # Create mapping of status to index
    status_to_idx = {status: i for i, status in enumerate(all_statuses)}
    
    # Create Sankey data
    source = [status_to_idx[status] for status in flow_counts['from_status']]
    target = [status_to_idx[status] for status in flow_counts['to_status']]
    value = flow_counts['count'].tolist()
    
    # Create the Sankey diagram
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=all_statuses
        ),
        link=dict(
            source=source,
            target=target,
            value=value
        )
    )])
    
    fig.update_layout(
        title='Issue Status Flow',
        font=dict(size=12)
    )
    
    return fig
