"""
Module for processing and analyzing YouTrack issue data.
"""
import os
import json
import logging
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from config import app_config

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataProcessor:
    """Process and analyze YouTrack issue data."""
    
    def __init__(self, raw_data_path: Optional[str] = None):
        """Initialize with path to raw data."""
        if raw_data_path is None:
            raw_data_path = os.path.join(app_config.data_dir, app_config.issues_file)
        self.raw_data_path = raw_data_path
        self.raw_data = None
        self.issues_df = None
        self.history_df = None
        self.comments_df = None
        self.sprint_df = None
        self.custom_fields_df = None
        
    def load_data(self) -> bool:
        """Load raw data from file."""
        try:
            if not os.path.exists(self.raw_data_path):
                logger.warning(f"Raw data file not found: {self.raw_data_path}")
                return False
                
            with open(self.raw_data_path, 'r') as f:
                self.raw_data = json.load(f)
                
            logger.info(f"Successfully loaded raw data from {self.raw_data_path}")
            return True
        except Exception as e:
            logger.error(f"Error loading raw data: {str(e)}", exc_info=True)
            return False
    
    def _extract_custom_fields(self, issues: List[Dict[str, Any]]) -> pd.DataFrame:
        """Extract custom fields from issues into a separate dataframe."""
        custom_fields_data = []
        
        for issue in issues:
            issue_id = issue.get('id')
            readable_id = issue.get('idReadable', '')  # Add support for readable ID from REST API
            
            for field in issue.get('customFields', []):
                field_name = field.get('name', '')
                field_id = field.get('id', '')
                
                # Extract value based on field type
                if 'value' in field:
                    value = field['value']
                    if isinstance(value, dict):
                        # For the latest REST API, try more fields
                        field_value = value.get('name', 
                                              value.get('text', 
                                                      value.get('localizedName',
                                                               value.get('presentation', ''))))
                    elif isinstance(value, list):
                        # Handle multi-value fields
                        field_value = [v.get('name', 
                                          v.get('text', 
                                               v.get('localizedName',
                                                    v.get('presentation', '')))) 
                                    for v in value if isinstance(v, dict)]
                        field_value = ", ".join(field_value) if field_value else ""
                    else:
                        field_value = str(value)
                else:
                    field_value = ""
                
                custom_fields_data.append({
                    'issue_id': issue_id,
                    'issue_readable_id': readable_id,  # Add readable ID for better reference
                    'field_id': field_id,
                    'field_name': field_name,
                    'field_value': field_value
                })
        
        return pd.DataFrame(custom_fields_data)
    
    def _extract_comments(self, issues: List[Dict[str, Any]]) -> pd.DataFrame:
        """Extract comments from issues into a separate dataframe with enhanced fields from REST API."""
        comments_data = []
        
        for issue in issues:
            issue_id = issue.get('id')
            readable_id = issue.get('idReadable', '')
            
            for comment in issue.get('comments', []):
                author = comment.get('author', {})
                author_name = author.get('name', author.get('login', 'Unknown'))
                author_email = author.get('email', '')
                author_id = author.get('id', '')
                
                comments_data.append({
                    'issue_id': issue_id,
                    'issue_readable_id': readable_id,
                    'comment_id': comment.get('id', ''),
                    'text': comment.get('text', ''),
                    'created': comment.get('created', ''),
                    'author_name': author_name,
                    'author_email': author_email,
                    'author_id': author_id
                })
        
        return pd.DataFrame(comments_data)
    
    def _process_issue_history(self, issue_histories: Dict[str, List[Dict[str, Any]]]) -> pd.DataFrame:
        """Process issue history data into a structured dataframe."""
        history_data = []
        
        for issue_id, activities in issue_histories.items():
            for activity in activities:
                author = activity.get('author', {})
                author_name = author.get('name', author.get('login', 'Unknown'))
                timestamp = activity.get('timestamp', '')
                
                target = activity.get('target', {})
                field = target.get('field', {})
                field_name = field.get('name', '')
                
                # For the latest REST API, the added/removed fields are more structured
                added_value = activity.get('added', {})
                removed_value = activity.get('removed', {})
                
                # Extract text values correctly based on type
                if isinstance(added_value, dict):
                    added = added_value.get('name', added_value.get('text', ''))
                elif isinstance(added_value, list) and added_value:
                    # Handle list of values
                    added_items = []
                    for item in added_value:
                        if isinstance(item, dict):
                            added_items.append(item.get('name', item.get('text', '')))
                        else:
                            added_items.append(str(item))
                    added = ', '.join(added_items)
                else:
                    added = str(added_value) if added_value else ''
                
                if isinstance(removed_value, dict):
                    removed = removed_value.get('name', removed_value.get('text', ''))
                elif isinstance(removed_value, list) and removed_value:
                    # Handle list of values
                    removed_items = []
                    for item in removed_value:
                        if isinstance(item, dict):
                            removed_items.append(item.get('name', item.get('text', '')))
                        else:
                            removed_items.append(str(item))
                    removed = ', '.join(removed_items)
                else:
                    removed = str(removed_value) if removed_value else ''
                
                category = activity.get('category', {})
                category_id = category.get('id', '') if isinstance(category, dict) else str(category)
                
                # Add more detail about the custom field if available
                custom_field = field.get('customField', {})
                field_type = ''
                if custom_field:
                    field_type_obj = custom_field.get('fieldType', {})
                    field_type = field_type_obj.get('name', '') if isinstance(field_type_obj, dict) else ''
                
                history_data.append({
                    'issue_id': issue_id,
                    'activity_id': activity.get('id', ''),
                    'timestamp': timestamp,
                    'author': author_name,
                    'field_name': field_name,
                    'field_type': field_type,
                    'category': category_id,
                    'added': added,
                    'removed': removed
                })
        
        return pd.DataFrame(history_data)
    
    def _extract_sprint_data(self, issues: List[Dict[str, Any]]) -> pd.DataFrame:
        """Extract sprint information from issues with enhanced data from REST API."""
        sprint_data = []
        
        for issue in issues:
            issue_id = issue.get('id')
            readable_id = issue.get('idReadable', '')
            sprint = issue.get('sprint', {})
            
            if sprint:
                # Extract enhanced sprint details available in the latest REST API
                sprint_data.append({
                    'issue_id': issue_id,
                    'issue_readable_id': readable_id,
                    'sprint_id': sprint.get('id', ''),
                    'sprint_name': sprint.get('name', ''),
                    'sprint_goal': sprint.get('goal', ''),
                    'sprint_start': sprint.get('start', ''),
                    'sprint_finish': sprint.get('finish', '')
                })
        
        # Also add sprint info from the main project data if available
        if self.raw_data and 'sprints' in self.raw_data:
            sprints = self.raw_data.get('sprints', [])
            for sprint in sprints:
                # Create a record with sprint details even if no issues are assigned yet
                # This ensures we see all sprints in the project
                if not any(sd['sprint_id'] == sprint.get('id', '') for sd in sprint_data):
                    sprint_data.append({
                        'issue_id': None,
                        'issue_readable_id': None,
                        'sprint_id': sprint.get('id', ''),
                        'sprint_name': sprint.get('name', ''),
                        'sprint_goal': sprint.get('goal', ''),
                        'sprint_start': sprint.get('start', ''),
                        'sprint_finish': sprint.get('finish', ''),
                        'sprint_status': sprint.get('status', ''),
                        'is_default': sprint.get('isDefault', False)
                    })
        
        return pd.DataFrame(sprint_data)
    
    def process_data(self) -> bool:
        """Process raw data into structured dataframes."""
        try:
            if self.raw_data is None and not self.load_data():
                return False
            
            # Extract issues
            issues = self.raw_data.get('issues', [])
            issue_histories = self.raw_data.get('issue_histories', {})
            
            # Create issues dataframe with additional fields from latest REST API
            issues_data = []
            for issue in issues:
                assignee = issue.get('assignee', {})
                assignee_name = assignee.get('name', assignee.get('login', '')) if assignee else ''
                
                # Extract reporter info
                reporter = issue.get('reporter', {})
                reporter_name = reporter.get('name', reporter.get('login', '')) if reporter else ''
                
                # Extract project info
                project = issue.get('project', {})
                project_name = project.get('name', '') if project else ''
                project_short_name = project.get('shortName', '') if project else ''
                
                # Extract time tracking data if available
                time_tracking = issue.get('timeTracking', {})
                work_items = time_tracking.get('workItems', []) if time_tracking else []
                total_time_spent = sum(item.get('duration', 0) for item in work_items) if work_items else 0
                
                # Extract link counts
                links = issue.get('links', [])
                subtasks = issue.get('subtasks', [])
                parent = issue.get('parent', {})
                has_parent = bool(parent.get('id', '')) if parent else False
                
                issues_data.append({
                    'id': issue.get('id', ''),
                    'readable_id': issue.get('idReadable', ''),  # New field from REST API
                    'summary': issue.get('summary', ''),
                    'description': issue.get('description', ''),
                    'created': issue.get('created', ''),
                    'updated': issue.get('updated', ''),
                    'resolved': issue.get('resolved', ''),
                    'assignee': assignee_name,
                    'reporter': reporter_name,
                    'project_name': project_name,
                    'project_short_name': project_short_name,
                    'tags': ', '.join([tag.get('name', '') for tag in issue.get('tags', [])]),
                    'time_spent': total_time_spent,
                    'link_count': len(links),
                    'subtask_count': len(subtasks),
                    'has_parent': has_parent
                })
            
            self.issues_df = pd.DataFrame(issues_data)
            
            # Process other data
            self.custom_fields_df = self._extract_custom_fields(issues)
            self.comments_df = self._extract_comments(issues)
            self.history_df = self._process_issue_history(issue_histories)
            self.sprint_df = self._extract_sprint_data(issues)
            
            # Convert timestamp strings to datetime objects
            for df in [self.issues_df, self.comments_df, self.history_df]:
                for col in df.columns:
                    if 'created' in col or 'updated' in col or 'resolved' in col or 'timestamp' in col:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
            
            # Save processed data
            self._save_processed_data()
            
            logger.info("Successfully processed raw data into structured dataframes")
            return True
            
        except Exception as e:
            logger.error(f"Error processing data: {str(e)}", exc_info=True)
            return False
    
    def _save_processed_data(self) -> None:
        """Save processed dataframes to a file."""
        # Define a custom JSON serializer for pandas Timestamp objects
        def json_serial(obj):
            """JSON serializer for objects not serializable by default json code"""
            if isinstance(obj, (pd.Timestamp, datetime)):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        processed_data = {
            'issues': self.issues_df.to_dict(orient='records') if self.issues_df is not None else [],
            'custom_fields': self.custom_fields_df.to_dict(orient='records') if self.custom_fields_df is not None else [],
            'comments': self.comments_df.to_dict(orient='records') if self.comments_df is not None else [],
            'history': self.history_df.to_dict(orient='records') if self.history_df is not None else [],
            'sprints': self.sprint_df.to_dict(orient='records') if self.sprint_df is not None else [],
            'processed_timestamp': datetime.now().isoformat()
        }
        
        output_path = os.path.join(app_config.data_dir, app_config.processed_data_file)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(processed_data, f, default=json_serial)
        
        logger.info(f"Saved processed data to {output_path}")
    
    def load_processed_data(self) -> bool:
        """Load previously processed data."""
        try:
            processed_data_path = os.path.join(app_config.data_dir, app_config.processed_data_file)
            
            if not os.path.exists(processed_data_path):
                logger.warning(f"Processed data file not found: {processed_data_path}")
                return False
            
            with open(processed_data_path, 'r') as f:
                processed_data = json.load(f)
            
            self.issues_df = pd.DataFrame(processed_data.get('issues', []))
            self.custom_fields_df = pd.DataFrame(processed_data.get('custom_fields', []))
            self.comments_df = pd.DataFrame(processed_data.get('comments', []))
            self.history_df = pd.DataFrame(processed_data.get('history', []))
            self.sprint_df = pd.DataFrame(processed_data.get('sprints', []))
            
            # Convert timestamp strings to datetime objects
            for df in [self.issues_df, self.comments_df, self.history_df]:
                for col in df.columns:
                    if 'created' in col or 'updated' in col or 'resolved' in col or 'timestamp' in col:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
            
            logger.info(f"Successfully loaded processed data from {processed_data_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error loading processed data: {str(e)}", exc_info=True)
            return False
    
    def get_status_transitions(self) -> pd.DataFrame:
        """Get status transitions from history data."""
        if self.history_df is None or self.history_df.empty:
            logger.warning("History data not available. Call process_data() first.")
            return pd.DataFrame()
            
        # Check if the required column exists
        if 'field_name' not in self.history_df.columns:
            logger.warning("field_name column not found in history data. Creating empty dataframe.")
            # Create an empty dataframe with the expected columns
            return pd.DataFrame(columns=['issue_id', 'activity_id', 'timestamp', 
                                        'author', 'field_name', 'field_type', 
                                        'category', 'added', 'removed', 'summary'])
        
        # Filter for 'State' field changes
        status_changes = self.history_df[self.history_df['field_name'] == 'State'].copy()
        
        # Add issue summary for better context
        if self.issues_df is not None and not self.issues_df.empty:
            status_changes = status_changes.merge(
                self.issues_df[['id', 'summary']], 
                left_on='issue_id', 
                right_on='id', 
                how='left'
            )
            if 'id' in status_changes.columns:
                status_changes.drop('id', axis=1, inplace=True)
        
        return status_changes
    
    def get_assignee_changes(self) -> pd.DataFrame:
        """Get assignee changes from history data."""
        if self.history_df is None or self.history_df.empty:
            logger.warning("History data not available. Call process_data() first.")
            return pd.DataFrame()
            
        # Check if the required column exists
        if 'field_name' not in self.history_df.columns:
            logger.warning("field_name column not found in history data. Creating empty dataframe.")
            # Create an empty dataframe with the expected columns
            return pd.DataFrame(columns=['issue_id', 'activity_id', 'timestamp', 
                                        'author', 'field_name', 'field_type', 
                                        'category', 'added', 'removed', 'summary'])
        
        # Filter for 'Assignee' field changes
        assignee_changes = self.history_df[self.history_df['field_name'] == 'Assignee'].copy()
        
        # Add issue summary for better context
        if self.issues_df is not None and not self.issues_df.empty:
            assignee_changes = assignee_changes.merge(
                self.issues_df[['id', 'summary']], 
                left_on='issue_id', 
                right_on='id', 
                how='left'
            )
            if 'id' in assignee_changes.columns:
                assignee_changes.drop('id', axis=1, inplace=True)
        
        return assignee_changes
    
    def get_issue_resolution_times(self) -> pd.DataFrame:
        """Calculate resolution times for resolved issues."""
        if self.issues_df is None:
            logger.warning("Issue data not available. Call process_data() first.")
            return pd.DataFrame()
        
        # Filter for resolved issues
        resolved_issues = self.issues_df.dropna(subset=['resolved']).copy()
        
        # Calculate resolution time
        resolved_issues['resolution_time'] = resolved_issues['resolved'] - resolved_issues['created']
        
        # Convert to days
        resolved_issues['resolution_days'] = resolved_issues['resolution_time'].dt.total_seconds() / (24 * 3600)
        
        return resolved_issues[['id', 'summary', 'created', 'resolved', 'resolution_days']]
    
    def get_sprint_statistics(self) -> Dict[str, Any]:
        """Calculate sprint statistics with enhanced data from latest REST API."""
        if self.sprint_df is None or self.issues_df is None or self.sprint_df.empty:
            logger.warning("Sprint or issue data not available. Call process_data() first.")
            return {}
        
        # Check if required column exists
        if 'sprint_name' not in self.sprint_df.columns:
            logger.warning("sprint_name column not found in sprint data.")
            return {}
            
        # Get unique sprints
        unique_sprints = self.sprint_df['sprint_name'].unique()
        
        sprint_stats = {}
        for sprint in unique_sprints:
            # Get representative sprint record for this sprint (for metadata)
            filtered_sprints = self.sprint_df[self.sprint_df['sprint_name'] == sprint]
            if filtered_sprints.empty:
                continue
                
            sprint_record = filtered_sprints.iloc[0].to_dict() if not filtered_sprints.empty else {}
            
            # Safety check - ensure we have a valid record
            if not sprint_record:
                continue
                
            # Get issues in this sprint
            sprint_issues = filtered_sprints['issue_id'].dropna().tolist() if 'issue_id' in filtered_sprints.columns else []
            
            # Get issue details
            sprint_issue_details = self.issues_df[self.issues_df['id'].isin(sprint_issues)] if sprint_issues and 'id' in self.issues_df.columns else pd.DataFrame()
            
            # Calculate statistics
            total_issues = len(sprint_issues)
            resolved_issues = sprint_issue_details.dropna(subset=['resolved']).shape[0] if not sprint_issue_details.empty and 'resolved' in sprint_issue_details.columns else 0
            
            # Safely extract time data with error handling
            try:
                sprint_start = pd.to_datetime(sprint_record.get('sprint_start', None), errors='coerce')
            except (TypeError, ValueError, AttributeError):
                sprint_start = None
                
            try:
                sprint_finish = pd.to_datetime(sprint_record.get('sprint_finish', None), errors='coerce')
            except (TypeError, ValueError, AttributeError):
                sprint_finish = None
            
            # Calculate time metrics if dates are available
            try:
                days_total = (sprint_finish - sprint_start).days if sprint_start is not None and sprint_finish is not None else None
            except (TypeError, AttributeError):
                days_total = None
                
            try:
                days_elapsed = (pd.Timestamp.now() - sprint_start).days if sprint_start is not None else None
            except (TypeError, AttributeError):
                days_elapsed = None
                
            try:
                days_remaining = (sprint_finish - pd.Timestamp.now()).days if sprint_finish is not None else None
            except (TypeError, AttributeError):
                days_remaining = None
            
            # Progress percentage
            try:
                progress_pct = (days_elapsed / days_total * 100) if days_total and days_elapsed is not None and days_total > 0 else None
            except (TypeError, ZeroDivisionError):
                progress_pct = None
            
            # Check if the sprint is current, past, or future
            now = pd.Timestamp.now()
            is_current = False
            is_past = False
            is_future = False
            
            if sprint_start is not None and sprint_finish is not None:
                try:
                    is_current = sprint_start <= now <= sprint_finish
                    is_past = now > sprint_finish
                    is_future = now < sprint_start
                except (TypeError, ValueError):
                    pass
            
            # Use safe get for dictionary keys that might not exist
            def safe_get(d, key, default=''):
                try:
                    return d.get(key, default)
                except (AttributeError, TypeError):
                    return default
            
            sprint_stats[sprint] = {
                'total_issues': total_issues,
                'resolved_issues': resolved_issues,
                'completion_rate': resolved_issues / total_issues if total_issues > 0 else 0,
                'sprint_goal': safe_get(sprint_record, 'sprint_goal'),
                'sprint_start': sprint_start,
                'sprint_finish': sprint_finish,
                'sprint_status': safe_get(sprint_record, 'sprint_status'),
                'is_current': is_current,
                'is_past': is_past,
                'is_future': is_future,
                'days_total': days_total,
                'days_elapsed': days_elapsed,
                'days_remaining': days_remaining,
                'progress_percentage': progress_pct
            }
        
        return sprint_stats
    
    def get_assignee_workload(self) -> pd.DataFrame:
        """Calculate current workload per assignee with additional metrics."""
        if self.issues_df is None or self.custom_fields_df is None:
            logger.warning("Issue data not available. Call process_data() first.")
            return pd.DataFrame()
        
        # Get unresolved issues
        unresolved_issues = self.issues_df[self.issues_df['resolved'].isna()].copy()
        
        # Create a more detailed assignee workload analysis
        assignee_stats = []
        
        # Get all assignees
        assignees = unresolved_issues['assignee'].unique()
        
        for assignee in assignees:
            if not assignee:  # Skip empty assignee
                continue
                
            # Get issues for this assignee
            assignee_issues = unresolved_issues[unresolved_issues['assignee'] == assignee]
            
            # Calculate various metrics
            total_issues = len(assignee_issues)
            
            # Try to get issue types from custom fields if available
            issue_ids = assignee_issues['id'].tolist()
            
            # Get custom fields for these issues
            issue_types = []
            issue_priorities = []
            
            # Extract Type and Priority fields from custom fields
            for issue_id in issue_ids:
                # Find Type field for this issue
                type_field = self.custom_fields_df[
                    (self.custom_fields_df['issue_id'] == issue_id) & 
                    (self.custom_fields_df['field_name'] == 'Type')
                ]
                if not type_field.empty:
                    issue_types.append(type_field.iloc[0]['field_value'])
                
                # Find Priority field for this issue
                priority_field = self.custom_fields_df[
                    (self.custom_fields_df['issue_id'] == issue_id) & 
                    (self.custom_fields_df['field_name'] == 'Priority')
                ]
                if not priority_field.empty:
                    issue_priorities.append(priority_field.iloc[0]['field_value'])
            
            # Count types and priorities
            type_counts = pd.Series(issue_types).value_counts().to_dict()
            priority_counts = pd.Series(issue_priorities).value_counts().to_dict()
            
            # Calculate high priority percentage
            high_priority_count = 0
            for priority, count in priority_counts.items():
                if 'critical' in priority.lower() or 'high' in priority.lower() or 'urgent' in priority.lower():
                    high_priority_count += count
            
            high_priority_pct = (high_priority_count / total_issues * 100) if total_issues > 0 else 0
            
            # Calculate recently updated issues (in last 7 days)
            now = pd.Timestamp.now()
            week_ago = now - pd.Timedelta(days=7)
            recent_issues = assignee_issues[assignee_issues['updated'] >= week_ago]
            recently_updated_count = len(recent_issues)
            
            # Add to stats
            assignee_stats.append({
                'assignee': assignee,
                'open_issues': total_issues,
                'types': type_counts,
                'priorities': priority_counts,
                'high_priority_percentage': high_priority_pct,
                'recently_updated_count': recently_updated_count,
                'recently_updated_percentage': (recently_updated_count / total_issues * 100) if total_issues > 0 else 0
            })
        
        return pd.DataFrame(assignee_stats)
