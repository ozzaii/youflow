"""
Module for generating AI-powered insights using Google's Gemini 2.0 model.
"""
import os
import logging
import json
import re
import google.generativeai as genai
from typing import Dict, List, Any, Optional
import pandas as pd
from datetime import datetime, timedelta

from config import app_config

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure Gemini API - Use the key from Mercedes project
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyARZyERqMaFInsbRKUA0NxOok77syBNzK8")
genai.configure(api_key=GEMINI_API_KEY)

class AIInsightsGenerator:
    """Generate insights from YouTrack data using Google's Gemini 2.0 AI model."""
    
    def __init__(self, model_name: str = "models/gemini-2.0-flash"):
        """Initialize with model configuration for Gemini 2.0.
        
        Args:
            model_name: The Gemini model to use. Default is 'models/gemini-2.0-flash' which supports
                        large context windows (up to 1M tokens) and has a knowledge cutoff of August 2024.
        """
        self.model_name = model_name
        # Configure the model with safety settings that allow more analytical content
        safety_settings = {
            "HARASSMENT": "block_none",
            "HATE": "block_none",
            "SEXUAL": "block_none",
            "DANGEROUS": "block_none",
        }
        self.model = genai.GenerativeModel(model_name, safety_settings=safety_settings)
        
    def _prepare_data_context(self, data_processor) -> Dict[str, Any]:
        """
        Prepare data context for the AI model.
        
        Args:
            data_processor: DataProcessor instance with loaded data
            
        Returns:
            Dictionary with structured data for the AI model
        """
        context = {}
        
        try:
            # Basic project stats
            if data_processor.issues_df is not None and not data_processor.issues_df.empty:
                # Check if required columns exist
                if 'resolved' not in data_processor.issues_df.columns:
                    logger.warning("Required column 'resolved' missing from issues dataframe")
                    total_issues = len(data_processor.issues_df)
                    open_issues = total_issues  # Assume all open if no resolved column
                    resolved_issues = 0
                else:
                    total_issues = len(data_processor.issues_df)
                    open_issues = data_processor.issues_df[data_processor.issues_df['resolved'].isna()].shape[0]
                    resolved_issues = total_issues - open_issues
                
                # Last 7 days stats
                week_ago = datetime.now() - timedelta(days=7)
                week_timestamp = pd.Timestamp(week_ago)
                
                # Last 30 days stats for better trend analysis
                month_ago = datetime.now() - timedelta(days=30)
                month_timestamp = pd.Timestamp(month_ago)
                
                # Check if required column exists
                if 'created' in data_processor.issues_df.columns:
                    # Weekly stats
                    recent_issues = data_processor.issues_df[data_processor.issues_df['created'] > week_timestamp]
                    recently_created = len(recent_issues)
                    
                    # Monthly stats
                    monthly_issues = data_processor.issues_df[data_processor.issues_df['created'] > month_timestamp]
                    monthly_created = len(monthly_issues)
                    
                    if 'resolved' in data_processor.issues_df.columns:
                        # Weekly resolutions
                        recent_resolutions = data_processor.issues_df[
                            (data_processor.issues_df['resolved'] > week_timestamp) & 
                            (data_processor.issues_df['resolved'].notna())
                        ]
                        recently_resolved = len(recent_resolutions)
                        
                        # Monthly resolutions
                        monthly_resolutions = data_processor.issues_df[
                            (data_processor.issues_df['resolved'] > month_timestamp) & 
                            (data_processor.issues_df['resolved'].notna())
                        ]
                        monthly_resolved = len(monthly_resolutions)
                    else:
                        recently_resolved = 0
                        monthly_resolved = 0
                else:
                    recently_created = 0
                    recently_resolved = 0
                    monthly_created = 0
                    monthly_resolved = 0
                
                # Identify stale issues (open more than 30 days)
                stale_issues = 0
                if 'created' in data_processor.issues_df.columns and 'resolved' in data_processor.issues_df.columns:
                    stale_mask = (
                        (data_processor.issues_df['created'] < month_timestamp) & 
                        (data_processor.issues_df['resolved'].isna())
                    )
                    stale_issues = stale_mask.sum()
                
                context["project_stats"] = {
                    "total_issues": total_issues,
                    "open_issues": open_issues,
                    "resolved_issues": resolved_issues,
                    "recently_created": recently_created,  # Last 7 days
                    "recently_resolved": recently_resolved,  # Last 7 days
                    "monthly_created": monthly_created,  # Last 30 days
                    "monthly_resolved": monthly_resolved,  # Last 30 days
                    "stale_issues": stale_issues  # Open > 30 days
                }
                
                # Calculate progress metrics
                if monthly_created > 0:
                    context["project_stats"]["monthly_completion_rate"] = round((monthly_resolved / monthly_created) * 100, 2)
                
                # Calculate net issue change rate
                context["project_stats"]["net_monthly_change"] = monthly_created - monthly_resolved
                context["project_stats"]["net_weekly_change"] = recently_created - recently_resolved
                
                # Add additional useful project statistics
                if 'created' in data_processor.issues_df.columns:
                    try:
                        # Calculate average issues created per week over the last 3 months
                        three_months_ago = datetime.now() - timedelta(days=90)
                        three_months_timestamp = pd.Timestamp(three_months_ago)
                        recent_period_issues = data_processor.issues_df[data_processor.issues_df['created'] > three_months_timestamp]
                        
                        if not recent_period_issues.empty:
                            weeks_span = (datetime.now() - three_months_ago).days / 7
                            issues_per_week = len(recent_period_issues) / max(1, weeks_span)
                            context["project_stats"]["avg_issues_per_week"] = round(issues_per_week, 2)
                            
                            # Calculate velocity metrics
                            if 'resolved' in data_processor.issues_df.columns:
                                recent_resolved_count = data_processor.issues_df[
                                    (data_processor.issues_df['resolved'] > three_months_timestamp) &
                                    (data_processor.issues_df['resolved'].notna())
                                ].shape[0]
                                
                                issues_resolved_per_week = recent_resolved_count / max(1, weeks_span)
                                context["project_stats"]["avg_issues_resolved_per_week"] = round(issues_resolved_per_week, 2)
                                
                                # Backlog growth/reduction rate 
                                context["project_stats"]["backlog_weekly_growth_rate"] = round(issues_per_week - issues_resolved_per_week, 2)
                                
                                # Estimated weeks to clear backlog at current velocity (if positive)
                                if issues_resolved_per_week > 0:
                                    weeks_to_clear = open_issues / issues_resolved_per_week
                                    context["project_stats"]["estimated_weeks_to_clear_backlog"] = round(weeks_to_clear, 1)
                    except Exception as e:
                        logger.warning(f"Error calculating weekly issue rate: {str(e)}")
                
                # Calculate average resolution time for resolved issues
                if 'resolved' in data_processor.issues_df.columns and 'created' in data_processor.issues_df.columns:
                    try:
                        resolved_issues_df = data_processor.issues_df[data_processor.issues_df['resolved'].notna()]
                        if not resolved_issues_df.empty:
                            resolved_issues_df['resolution_time'] = resolved_issues_df['resolved'] - resolved_issues_df['created']
                            
                            # Overall average
                            avg_resolution_time = resolved_issues_df['resolution_time'].mean()
                            context["project_stats"]["avg_resolution_days"] = round(avg_resolution_time.total_seconds() / (3600 * 24), 2)
                            
                            # Recent trend (last 30 days)
                            recent_resolved = resolved_issues_df[resolved_issues_df['resolved'] > month_timestamp]
                            if not recent_resolved.empty:
                                recent_avg_resolution = recent_resolved['resolution_time'].mean()
                                context["project_stats"]["recent_avg_resolution_days"] = round(recent_avg_resolution.total_seconds() / (3600 * 24), 2)
                                
                                # Calculate if resolution time is improving
                                is_improving = recent_avg_resolution < avg_resolution_time
                                context["project_stats"]["resolution_time_improving"] = is_improving
                    except Exception as e:
                        logger.warning(f"Error calculating average resolution time: {str(e)}")
            else:
                context["project_stats"] = {
                    "total_issues": 0,
                    "open_issues": 0,
                    "resolved_issues": 0,
                    "recently_created": 0,
                    "recently_resolved": 0
                }
        except Exception as e:
            logger.error(f"Error preparing project stats context: {str(e)}", exc_info=True)
            context["project_stats"] = {
                "total_issues": 0,
                "open_issues": 0,
                "resolved_issues": 0,
                "recently_created": 0,
                "recently_resolved": 0,
                "error": str(e)
            }
        
        try:
            # Status distribution
            if (data_processor.custom_fields_df is not None and 
                not data_processor.custom_fields_df.empty and
                'field_name' in data_processor.custom_fields_df.columns and
                'field_value' in data_processor.custom_fields_df.columns):
                
                status_field = data_processor.custom_fields_df[data_processor.custom_fields_df['field_name'] == 'State']
                if not status_field.empty:
                    status_counts = status_field['field_value'].value_counts().to_dict()
                    context["status_distribution"] = status_counts
                    
                    # Add status breakdown by percentage
                    total = sum(status_counts.values())
                    if total > 0:
                        status_percentage = {status: round(count/total * 100, 2) for status, count in status_counts.items()}
                        context["status_percentage"] = status_percentage
                else:
                    context["status_distribution"] = {}
                    context["status_percentage"] = {}
                
                # Extract priority distribution if available
                priority_field = data_processor.custom_fields_df[data_processor.custom_fields_df['field_name'] == 'Priority']
                if not priority_field.empty:
                    priority_counts = priority_field['field_value'].value_counts().to_dict()
                    context["priority_distribution"] = priority_counts
                
                # Extract type distribution if available
                type_field = data_processor.custom_fields_df[data_processor.custom_fields_df['field_name'] == 'Type']
                if not type_field.empty:
                    type_counts = type_field['field_value'].value_counts().to_dict()
                    context["issue_type_distribution"] = type_counts
            else:
                context["status_distribution"] = {}
                context["status_percentage"] = {}
                context["priority_distribution"] = {}
                context["issue_type_distribution"] = {}
        except Exception as e:
            logger.error(f"Error preparing status distribution context: {str(e)}", exc_info=True)
            context["status_distribution"] = {"error": str(e)}
        
        try:
            # Assignee workload
            assignee_workload = data_processor.get_assignee_workload()
            if not assignee_workload.empty:
                context["assignee_workload"] = assignee_workload.to_dict(orient='records')
                
                # Add team metrics
                context["team_metrics"] = {
                    "total_team_members": len(assignee_workload),
                    "avg_issues_per_member": round(assignee_workload['open_issues'].mean(), 2),
                    "max_issues_assigned": assignee_workload['open_issues'].max(),
                    "min_issues_assigned": assignee_workload['open_issues'].min()
                }
            else:
                context["assignee_workload"] = []
                context["team_metrics"] = {}
        except Exception as e:
            logger.error(f"Error preparing assignee workload context: {str(e)}", exc_info=True)
            context["assignee_workload"] = [{"error": str(e)}]
            context["team_metrics"] = {"error": str(e)}
        
        try:
            # Sprint statistics
            sprint_stats = data_processor.get_sprint_statistics()
            if sprint_stats:
                # Convert datetime objects to strings for JSON serialization
                for sprint, stats in sprint_stats.items():
                    for key, value in stats.items():
                        if isinstance(value, (pd.Timestamp, datetime)):
                            sprint_stats[sprint][key] = value.isoformat()
                context["sprint_statistics"] = sprint_stats
                
                # Add additional sprint analytics
                active_sprints = {name: stats for name, stats in sprint_stats.items() 
                                 if stats.get('status') == 'active'}
                completed_sprints = {name: stats for name, stats in sprint_stats.items() 
                                    if stats.get('status') == 'completed'}
                
                if active_sprints:
                    context["active_sprints_count"] = len(active_sprints)
                    
                if completed_sprints:
                    completion_rates = [stats.get('completion_rate', 0) for stats in completed_sprints.values()]
                    if completion_rates:
                        context["avg_sprint_completion_rate"] = round(sum(completion_rates) / len(completion_rates), 2)
            else:
                context["sprint_statistics"] = {}
        except Exception as e:
            logger.error(f"Error preparing sprint statistics context: {str(e)}", exc_info=True)
            context["sprint_statistics"] = {"error": str(e)}
        
        try:
            # Recent activity
            if (data_processor.history_df is not None and 
                not data_processor.history_df.empty and
                'timestamp' in data_processor.history_df.columns):
                
                recent_cutoff = pd.Timestamp.now() - pd.Timedelta(days=7)
                recent_activity = data_processor.history_df[data_processor.history_df['timestamp'] > recent_cutoff].copy()
                
                if not recent_activity.empty:
                    # Sort by timestamp (most recent first)
                    recent_activity = recent_activity.sort_values('timestamp', ascending=False)
                    
                    # Add issue summary if possible
                    if (data_processor.issues_df is not None and 
                        not data_processor.issues_df.empty and
                        'id' in data_processor.issues_df.columns and 
                        'summary' in data_processor.issues_df.columns and
                        'issue_id' in recent_activity.columns):
                        
                        recent_activity = recent_activity.merge(
                            data_processor.issues_df[['id', 'summary']],
                            left_on='issue_id',
                            right_on='id',
                            how='left'
                        )
                    
                    # Convert to records - handle datetime serialization
                    activity_records = []
                    for _, row in recent_activity.head(50).iterrows():
                        record = {}
                        for col, val in row.items():
                            if isinstance(val, (pd.Timestamp, datetime)):
                                record[col] = val.isoformat()
                            else:
                                record[col] = val
                        activity_records.append(record)
                    
                    context["recent_activity"] = activity_records
                    
                    # Add activity trend analysis
                    if len(activity_records) > 0:
                        # Count activities by type
                        field_types = recent_activity['field_name'].value_counts().to_dict()
                        context["activity_by_field"] = field_types
                        
                        # Most active users
                        if 'author' in recent_activity.columns:
                            most_active_users = recent_activity['author'].value_counts().head(5).to_dict()
                            context["most_active_users"] = most_active_users
                else:
                    context["recent_activity"] = []
                    context["activity_by_field"] = {}
                    context["most_active_users"] = {}
            else:
                context["recent_activity"] = []
                context["activity_by_field"] = {}
                context["most_active_users"] = {}
        except Exception as e:
            logger.error(f"Error preparing recent activity context: {str(e)}", exc_info=True)
            context["recent_activity"] = [{"error": str(e)}]
            context["activity_by_field"] = {"error": str(e)}
            context["most_active_users"] = {"error": str(e)}
        
        # Add samples of both recent and open issues for better context
        try:
            if data_processor.issues_df is not None and not data_processor.issues_df.empty:
                # Get sample of recent issues (up to 10)
                if 'created' in data_processor.issues_df.columns:
                    # Sort by creation date (most recent first)
                    recent_issues = data_processor.issues_df.sort_values('created', ascending=False).head(10)
                else:
                    # If no created date, just take the first 10
                    recent_issues = data_processor.issues_df.head(10)
                
                # Get sample of open issues with highest priority (up to 10)
                open_issues = None
                if 'resolved' in data_processor.issues_df.columns:
                    open_issues = data_processor.issues_df[data_processor.issues_df['resolved'].isna()]
                    
                    # Try to sort by priority if available
                    if data_processor.custom_fields_df is not None and not data_processor.custom_fields_df.empty:
                        try:
                            # Find priority field
                            priority_field = data_processor.custom_fields_df[
                                data_processor.custom_fields_df['field_name'] == 'Priority'
                            ]
                            
                            if not priority_field.empty:
                                # Get unique issue_ids with priorities
                                priority_mapping = {}
                                for _, row in priority_field.iterrows():
                                    # Convert priority values to numeric for sorting
                                    # Higher values for higher priorities like "Critical" and "High"
                                    priority_value = 0
                                    if row['field_value'] == 'Critical':
                                        priority_value = 100
                                    elif row['field_value'] == 'High':
                                        priority_value = 75
                                    elif row['field_value'] == 'Normal':
                                        priority_value = 50
                                    elif row['field_value'] == 'Low':
                                        priority_value = 25
                                    
                                    priority_mapping[row['issue_id']] = priority_value
                                
                                # Add priority values to open issues for sorting
                                open_issues_list = []
                                for _, issue in open_issues.iterrows():
                                    issue_id = issue['id'] if 'id' in issue else None
                                    if issue_id and issue_id in priority_mapping:
                                        issue_dict = issue.to_dict()
                                        issue_dict['_priority_value'] = priority_mapping[issue_id]
                                        open_issues_list.append(issue_dict)
                                
                                # Sort by priority (highest first)
                                if open_issues_list:
                                    open_issues_list.sort(key=lambda x: x.get('_priority_value', 0), reverse=True)
                                    open_issues_sample = pd.DataFrame(open_issues_list[:10])
                                else:
                                    open_issues_sample = open_issues.head(10)
                            else:
                                open_issues_sample = open_issues.head(10)
                        except Exception as e:
                            logger.warning(f"Error sorting open issues by priority: {str(e)}")
                            open_issues_sample = open_issues.head(10)
                    else:
                        open_issues_sample = open_issues.head(10)
                
                # Create a simplified version with essential fields
                recent_samples = []
                open_samples = []
                stale_samples = []
                
                # Enhanced fields list to provide more context for the AI
                essential_fields = [
                    'id', 'readable_id', 'summary', 'description', 'created', 'updated', 'resolved', 
                    'assignee', 'reporter', 'tags', 'comments'
                ]
                
                # Process recent issues
                for _, issue in recent_issues.iterrows():
                    sample = {}
                    for field in essential_fields:
                        if field in issue and not pd.isna(issue[field]):
                            if isinstance(issue[field], (pd.Timestamp, datetime)):
                                sample[field] = issue[field].isoformat()
                            else:
                                sample[field] = issue[field]
                    
                    # Add custom fields like priority, state, type if available
                    if data_processor.custom_fields_df is not None:
                        issue_custom_fields = data_processor.custom_fields_df[
                            data_processor.custom_fields_df['issue_id'] == issue['id']
                        ]
                        if not issue_custom_fields.empty:
                            for _, cf_row in issue_custom_fields.iterrows():
                                field_name = cf_row['field_name']
                                field_value = cf_row['field_value']
                                if field_name and field_value:
                                    sample[field_name.lower()] = field_value
                    
                    recent_samples.append(sample)
                
                # Process open issues if available
                open_issues_sample = None  # Initialize with None
                try:
                    # Check if we have any open issues to process
                    if open_issues is not None and not open_issues.empty:
                        # Use the first 10 open issues (we'll initialize this regardless)
                        open_issues_sample = open_issues.head(10)
                except Exception as e:
                    logger.warning(f"Error creating open issues sample: {str(e)}")
                    open_issues_sample = None
                
                if open_issues_sample is not None and not open_issues_sample.empty:
                    for _, issue in open_issues_sample.iterrows():
                        sample = {}
                        for field in essential_fields:
                            if field in issue and not pd.isna(issue[field]):
                                if isinstance(issue[field], (pd.Timestamp, datetime)):
                                    sample[field] = issue[field].isoformat()
                                else:
                                    sample[field] = issue[field]
                        
                        # Add custom fields like priority, state, type if available
                        if data_processor.custom_fields_df is not None:
                            issue_custom_fields = data_processor.custom_fields_df[
                                data_processor.custom_fields_df['issue_id'] == issue['id']
                            ]
                            if not issue_custom_fields.empty:
                                for _, cf_row in issue_custom_fields.iterrows():
                                    field_name = cf_row['field_name']
                                    field_value = cf_row['field_value']
                                    if field_name and field_value:
                                        sample[field_name.lower()] = field_value
                        
                        open_samples.append(sample)
                
                # Find stale issues (open for >30 days)
                if open_issues is not None and not open_issues.empty and 'created' in open_issues.columns:
                    month_ago = datetime.now() - timedelta(days=30)
                    stale_issues = open_issues[open_issues['created'] < pd.Timestamp(month_ago)]
                    
                    if not stale_issues.empty:
                        for _, issue in stale_issues.head(5).iterrows():
                            sample = {}
                            for field in essential_fields:
                                if field in issue and not pd.isna(issue[field]):
                                    if isinstance(issue[field], (pd.Timestamp, datetime)):
                                        sample[field] = issue[field].isoformat()
                                    else:
                                        sample[field] = issue[field]
                                        
                            # Calculate age in days
                            if 'created' in issue and not pd.isna(issue['created']):
                                days_open = (datetime.now() - issue['created'].to_pydatetime()).days
                                sample['days_open'] = days_open
                            
                            # Add custom fields
                            if data_processor.custom_fields_df is not None:
                                issue_custom_fields = data_processor.custom_fields_df[
                                    data_processor.custom_fields_df['issue_id'] == issue['id']
                                ]
                                if not issue_custom_fields.empty:
                                    for _, cf_row in issue_custom_fields.iterrows():
                                        field_name = cf_row['field_name']
                                        field_value = cf_row['field_value']
                                        if field_name and field_value:
                                            sample[field_name.lower()] = field_value
                            
                            stale_samples.append(sample)
                
                # Combine all samples into the context
                context["recent_issue_samples"] = recent_samples
                context["open_issue_samples"] = open_samples
                context["stale_issue_samples"] = stale_samples
                
                # For backward compatibility
                context["issue_samples"] = recent_samples
            else:
                context["recent_issue_samples"] = []
                context["open_issue_samples"] = []
                context["stale_issue_samples"] = []
                context["issue_samples"] = []
        except Exception as e:
            logger.error(f"Error preparing issue samples: {str(e)}", exc_info=True)
            context["recent_issue_samples"] = [{"error": str(e)}]
            context["open_issue_samples"] = []
            context["stale_issue_samples"] = []
            context["issue_samples"] = [{"error": str(e)}]
        
        return context
    
    def generate_daily_report(self, data_processor) -> Dict[str, Any]:
        """
        Generate a daily insight report.
        
        Args:
            data_processor: DataProcessor instance with loaded data
            
        Returns:
            Dictionary with sections of insights
        """
        logger.info("Generating daily AI insights report")
        
        # Check if API key is configured
        if not GEMINI_API_KEY:
            logger.warning("Gemini API key not configured, skipping AI insights")
            return {
                "error": "Gemini API key not configured. Please set the GEMINI_API_KEY environment variable."
            }
        
        try:
            # Prepare data context
            context = self._prepare_data_context(data_processor)
            
            # Create prompt
            system_prompt = """
            You are an expert project analyst working with YouTrack data for the Mercedes "MQ EIS/KG BSW" project.
            Your task is to analyze the provided project data and generate actionable insights.
            Focus on identifying trends, risks, and opportunities. Be specific and concrete in your analysis.
            
            Important Context: 
            - The data has been optimized to provide comprehensive details on all OPEN issues while providing summary information for CLOSED issues.
            - Open issues include full comment history, status transitions, and detailed activity logs.
            - Closed issues include basic metadata, final status, and time tracking totals.
            - Base your analysis primarily on currently open and active issues where action is still possible.
            - Use closed issue data for trend analysis and identifying historical patterns.
            
            Structure your response in the following sections:
            1. Executive Summary: 2-3 sentence overview of the current project status
            2. Key Metrics: Highlight important metrics and their implications
            3. Risks & Bottlenecks: Identify potential issues that need attention
            4. Recommendations: Provide 3-5 actionable recommendations based on the data
            5. Team Performance: Analyze team velocity and individual contributions
            
            For your analysis:
            - Prioritize insights related to current open issues where action can be taken
            - Focus on identifying bottlenecks and improving efficiency for active work
            - Use issue samples provided to highlight specific examples when relevant
            - Analyze work distribution and team workload for resource optimization
            - Consider sprint forecasting if sprint data is available
            
            Keep your analysis professional, data-driven, and actionable. Avoid generic statements.
            """
            
            user_prompt = f"""
            Here is the current project data (as of {datetime.now().strftime('%Y-%m-%d')}):
            
            {json.dumps(context, indent=2)}
            
            Analyze this data and provide insights based on the structure described in the system prompt.
            """
            
            # Generate insights
            response = self.model.generate_content(
                [system_prompt, user_prompt],
                generation_config={
                    "temperature": 0.2,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 4096,
                }
            )
            
            # Process and structure the response
            raw_insights = response.text
            
            # Check if any data is available before attempting to parse
            project_stats = context.get('project_stats', {})
            if (project_stats.get('total_issues', 0) == 0 or 
                not context.get('status_distribution') or 
                not context.get('assignee_workload')):
                
                # Create a basic summary from the limited available data
                sections = {
                    "executive_summary": "Limited data is available for analysis. Please refresh the data or check API connection settings.",
                    "key_metrics": f"Total issues: {project_stats.get('total_issues', 0)}. No detailed metrics are available due to limited data.",
                    "risks_bottlenecks": "Unable to identify risks and bottlenecks due to insufficient data.",
                    "recommendations": "1. Verify YouTrack API connection settings.\n2. Check that you have selected the correct project ID.\n3. Ensure your API token has sufficient permissions.",
                    "team_performance": "Team performance analysis requires issue assignee data which is currently not available."
                }
                logger.info("Generated basic insights with limited data")
                return sections
            
            # Split into sections (more robust parsing that handles various formats)
            sections = {}
            text_blocks = raw_insights.split('\n\n')
            
            # Initialize default section content for fallback
            default_content = {
                "executive_summary": "Analysis of the YouTrack data shows limited information for comprehensive insights.",
                "key_metrics": "No detailed metrics could be derived from the current data.",
                "risks_bottlenecks": "Insufficient data to identify specific risks and bottlenecks.",
                "recommendations": "Review the data quality and completeness to enable better insights.",
                "team_performance": "Team performance analysis requires additional data."
            }
            
            # Match sections using more flexible patterns
            current_section = None
            section_patterns = {
                r"executive\s*summary|summary|overview": "executive_summary",
                r"key\s*metrics|metrics|statistics": "key_metrics",
                r"risks|bottlenecks|issues|challenges|problems": "risks_bottlenecks",
                r"recommendations|suggestions|actions": "recommendations",
                r"team\s*performance|performance|team": "team_performance"
            }
            
            # Process each paragraph
            for block in text_blocks:
                block = block.strip()
                if not block:
                    continue
                    
                # Try to identify section headers
                section_found = False
                for pattern, section_name in section_patterns.items():
                    # Check if this block is a new section header
                    if (re.search(r"^\d+[\.\)]\s*" + pattern, block.lower(), re.IGNORECASE) or
                        re.search(r"^" + pattern + r"\s*[:,]", block.lower(), re.IGNORECASE)):
                        current_section = section_name
                        section_found = True
                        # Don't include the header line in the content
                        # Instead, add the rest of the block if it contains more than the header
                        content_lines = block.split('\n')[1:]
                        if content_lines:
                            sections[current_section] = '\n'.join(content_lines).strip()
                        else:
                            sections[current_section] = ""
                        break
                
                # If it's not a section header and we have a current section, add to that section
                if not section_found and current_section:
                    if current_section in sections:
                        sections[current_section] += "\n\n" + block
                    else:
                        sections[current_section] = block
            
            # If no sections were identified or some are missing, use the whole text
            if not sections:
                logger.warning("Failed to parse AI response into sections")
                # Try to split it into reasonable sections
                lines = raw_insights.split('\n')
                current_section = "executive_summary"  # Start with executive summary
                for i, line in enumerate(lines):
                    if i < len(lines) // 5:
                        if current_section in sections:
                            sections[current_section] += "\n" + line
                        else:
                            sections[current_section] = line
                    elif i < 2 * len(lines) // 5:
                        current_section = "key_metrics"
                        if current_section in sections:
                            sections[current_section] += "\n" + line
                        else:
                            sections[current_section] = line
                    elif i < 3 * len(lines) // 5:
                        current_section = "risks_bottlenecks"
                        if current_section in sections:
                            sections[current_section] += "\n" + line
                        else:
                            sections[current_section] = line
                    elif i < 4 * len(lines) // 5:
                        current_section = "recommendations"
                        if current_section in sections:
                            sections[current_section] += "\n" + line
                        else:
                            sections[current_section] = line
                    else:
                        current_section = "team_performance"
                        if current_section in sections:
                            sections[current_section] += "\n" + line
                        else:
                            sections[current_section] = line
            
            # Fill in any missing sections with defaults
            for section, content in default_content.items():
                if section not in sections or not sections[section].strip():
                    sections[section] = content
            
            logger.info("Successfully generated AI insights")
            return sections
            
        except Exception as e:
            logger.error(f"Error generating AI insights: {str(e)}", exc_info=True)
            return {
                "error": f"Failed to generate insights: {str(e)}"
            }
    
    def analyze_issue_trends(self, data_processor) -> Dict[str, Any]:
        """
        Analyze issue trends over time.
        
        Args:
            data_processor: DataProcessor instance with loaded data
            
        Returns:
            Dictionary with trend analysis
        """
        logger.info("Analyzing issue trends with AI")
        
        # Check if API key is configured
        if not GEMINI_API_KEY:
            logger.warning("Gemini API key not configured, skipping trend analysis")
            return {
                "error": "Gemini API key not configured. Please set the GEMINI_API_KEY environment variable."
            }
        
        try:
            # Prepare time-series data
            if data_processor.issues_df is None or data_processor.issues_df.empty:
                return {"error": "No issue data available for trend analysis"}
            
            # Create weekly issue data
            issues_df = data_processor.issues_df.copy()
            issues_df['created_week'] = issues_df['created'].dt.to_period('W').dt.start_time
            weekly_created = issues_df.groupby('created_week').size().reset_index()
            weekly_created.columns = ['week', 'created_count']
            
            # Calculate weekly resolved
            resolved_df = issues_df.dropna(subset=['resolved']).copy()
            if not resolved_df.empty:
                resolved_df['resolved_week'] = resolved_df['resolved'].dt.to_period('W').dt.start_time
                weekly_resolved = resolved_df.groupby('resolved_week').size().reset_index()
                weekly_resolved.columns = ['week', 'resolved_count']
                
                # Merge created and resolved
                weekly_data = weekly_created.merge(weekly_resolved, left_on='week', right_on='week', how='outer').fillna(0)
                weekly_data = weekly_data.sort_values('week')
                
                # Convert to records
                trend_data = weekly_data.to_dict(orient='records')
            else:
                trend_data = weekly_created.to_dict(orient='records')
            
            # Create prompt
            prompt = f"""
            Analyze the following weekly issue creation and resolution data for the Mercedes project:
            
            {json.dumps(trend_data, indent=2, default=str)}
            
            Please provide:
            1. An analysis of overall trends in issue creation and resolution
            2. Identification of any anomalies or concerning patterns
            3. Predictions for future trends based on historical data
            4. Recommendations for improving project velocity
            
            Focus on actionable insights and data-driven observations.
            """
            
            # Generate analysis
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 2048,
                }
            )
            
            logger.info("Successfully generated trend analysis")
            return {
                "trend_data": trend_data,
                "analysis": response.text
            }
            
        except Exception as e:
            logger.error(f"Error analyzing issue trends: {str(e)}", exc_info=True)
            return {
                "error": f"Failed to analyze trends: {str(e)}"
            }
    
    def generate_followup_questions(self, data_processor) -> List[str]:
        """
        Generate follow-up questions for project managers based on data analysis.
        
        Args:
            data_processor: DataProcessor instance with loaded data
            
        Returns:
            List of follow-up questions
        """
        logger.info("Generating follow-up questions with AI")
        
        # Check if API key is configured
        if not GEMINI_API_KEY:
            logger.warning("Gemini API key not configured, skipping question generation")
            return ["Gemini API key not configured. Please set the GEMINI_API_KEY environment variable."]
        
        try:
            # Prepare context
            context = self._prepare_data_context(data_processor)
            
            prompt = f"""
            Based on the following YouTrack project data:
            
            {json.dumps(context, indent=2, default=str)}
            
            Generate 5 important follow-up questions that a project manager should ask to better understand the current project status and potential issues.
            
            Return just the numbered list of questions without any additional text.
            """
            
            # Generate questions
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 1024,
                }
            )
            
            # Parse the questions
            questions = []
            for line in response.text.split('\n'):
                if line.strip() and (line.strip()[0].isdigit() or line.strip()[0] == '#'):
                    questions.append(line.strip())
            
            logger.info(f"Generated {len(questions)} follow-up questions")
            return questions if questions else ["No questions could be generated from the available data."]
            
        except Exception as e:
            logger.error(f"Error generating follow-up questions: {str(e)}", exc_info=True)
            return [f"Error generating questions: {str(e)}"]