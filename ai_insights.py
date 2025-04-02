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
    
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        """Initialize with model configuration for Gemini 2.0.
        
        Args:
            model_name: The Gemini model to use. Default is 'gemini-1.5-flash' which supports
                        large context windows (up to 1M tokens).
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
                
                # Check if required column exists
                if 'created' in data_processor.issues_df.columns:
                    recent_issues = data_processor.issues_df[data_processor.issues_df['created'] > week_timestamp]
                    recently_created = len(recent_issues)
                    
                    if 'resolved' in data_processor.issues_df.columns:
                        recent_resolutions = data_processor.issues_df[
                            (data_processor.issues_df['resolved'] > week_timestamp) & 
                            (data_processor.issues_df['resolved'].notna())
                        ]
                        recently_resolved = len(recent_resolutions)
                    else:
                        recently_resolved = 0
                else:
                    recently_created = 0
                    recently_resolved = 0
                
                context["project_stats"] = {
                    "total_issues": total_issues,
                    "open_issues": open_issues,
                    "resolved_issues": resolved_issues,
                    "recently_created": recently_created,
                    "recently_resolved": recently_resolved
                }
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
                else:
                    context["status_distribution"] = {}
            else:
                context["status_distribution"] = {}
        except Exception as e:
            logger.error(f"Error preparing status distribution context: {str(e)}", exc_info=True)
            context["status_distribution"] = {"error": str(e)}
        
        try:
            # Assignee workload
            assignee_workload = data_processor.get_assignee_workload()
            if not assignee_workload.empty:
                context["assignee_workload"] = assignee_workload.to_dict(orient='records')
            else:
                context["assignee_workload"] = []
        except Exception as e:
            logger.error(f"Error preparing assignee workload context: {str(e)}", exc_info=True)
            context["assignee_workload"] = [{"error": str(e)}]
        
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
                else:
                    context["recent_activity"] = []
            else:
                context["recent_activity"] = []
        except Exception as e:
            logger.error(f"Error preparing recent activity context: {str(e)}", exc_info=True)
            context["recent_activity"] = [{"error": str(e)}]
        
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
            
            Structure your response in the following sections:
            1. Executive Summary: 2-3 sentence overview of the current project status
            2. Key Metrics: Highlight important metrics and their implications
            3. Risks & Bottlenecks: Identify potential issues that need attention
            4. Recommendations: Provide 3-5 actionable recommendations based on the data
            5. Team Performance: Analyze team velocity and individual contributions
            
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