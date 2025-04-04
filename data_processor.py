"""
Module for processing and analyzing YouTrack issue data.
"""
import os
import json
import logging
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from config import app_config, youtrack_config

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataProcessor:
    """Process and analyze YouTrack issue data."""
    
    def __init__(self, raw_data_dict: Optional[Dict[str, Any]] = None, raw_data_path: str = "data/raw_youtrack_data.json"):
        """Initialize the DataProcessor.

        Args:
            raw_data_dict: Optional dictionary containing the raw data fetched from the API.
                           If provided, this data is used directly.
            raw_data_path: Path to the raw JSON data file. Used if raw_data_dict is not provided.
        """
        self.raw_data_path = raw_data_path
        self.raw_data: Optional[Dict[str, Any]] = raw_data_dict
        self.processed_data_path = os.path.join(app_config.data_dir, app_config.processed_data_file)
        self.issues_df: Optional[pd.DataFrame] = None
        self.custom_fields_df: Optional[pd.DataFrame] = None
        self.comments_df: Optional[pd.DataFrame] = None
        self.activities_raw: List[Dict[str, Any]] = []
        self.recent_activity_df: Optional[pd.DataFrame] = None
        self.sprint_df: Optional[pd.DataFrame] = None
        self.custom_field_values: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self.metrics_24h: Dict[str, int] = {}
        self.metrics_overall: Dict[str, Any] = {}
        
        if self.raw_data:
            logger.info("DataProcessor initialized with provided raw data dictionary.")
            self.activities_raw = self.raw_data.get('activities', [])
            self.custom_field_values = self.raw_data.get('custom_field_values', {})
        else:
            logger.info(f"DataProcessor initialized. Will attempt to load raw data from {self.raw_data_path}")
            self.load_raw_data()
        
    def load_raw_data(self):
        """Loads the raw data from the specified JSON file."""
        if not os.path.exists(self.raw_data_path):
            logger.error(f"Raw data file not found: {self.raw_data_path}")
            self.raw_data = None
            return
        try:
            with open(self.raw_data_path, 'r') as f:
                self.raw_data = json.load(f)
            logger.info(f"Successfully loaded raw data from {self.raw_data_path}")
            if self.raw_data:
                self.activities_raw = self.raw_data.get('activities', [])
                self.custom_field_values = self.raw_data.get('custom_field_values', {})
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {self.raw_data_path}: {e}")
            self.raw_data = None
        except Exception as e:
            logger.error(f"Error reading raw data file {self.raw_data_path}: {e}")
            self.raw_data = None
    
    def _create_issues_dataframe(self, issues: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Creates the main issues dataframe and the custom fields dataframe."""
        if not issues:
            logger.warning("No issues provided to _create_issues_dataframe.")
            return pd.DataFrame(), pd.DataFrame()
            
        issues_data = []
        custom_fields_data = []

        for issue in issues:
            # Base issue details
            base_details = {
                "id": issue.get("id"),
                "idReadable": issue.get("idReadable"),
                "summary": issue.get("summary", "").strip(),
                "description": issue.get("description", "").strip() if issue.get("description") else None,
                "created": pd.to_datetime(issue.get("created"), unit='ms', errors='coerce'),
                "updated": pd.to_datetime(issue.get("updated"), unit='ms', errors='coerce'),
                "resolved": pd.to_datetime(issue.get("resolved"), unit='ms', errors='coerce')
            }

            # Extract custom fields and find Assignee specifically
            assignee_name = "Unassigned" # Default
            if issue.get("customFields"): # Check if customFields exists and is not None
                for field in issue["customFields"]:
                    if not field: # Skip if field is None
                        continue

                    # --- CORRECTED Field Name Extraction --- #
                    # The 'name' seems to be directly in the field object based on grep results
                    field_name = field.get("name")
                    # --- End Correction ---

                    field_value = field.get("value")
                    value_type = field.get("$type") # Get the type of the value

                    if field_name:
                        # Store all custom fields for potential later use/merging
                        cf_entry = {
                            "issue_id": base_details["id"],
                            "field_name": field_name,
                            "value": None, # Initialize
                            "value_type": value_type
                        }

                        # Extract value based on type
                        if isinstance(field_value, dict):
                            # Handle User, StateBundleElement, EnumBundleElement, etc.
                            cf_entry["value_id"] = field_value.get("id")
                            cf_entry["value_name"] = field_value.get("name") or field_value.get("login") # Use name or login
                            cf_entry["value"] = cf_entry["value_name"] # Simplified value
                        elif isinstance(field_value, list):
                             # Handle multi-value fields (e.g., multiple assignees, tags)
                             # For simplicity, join names or logins if available, otherwise store the list
                             names = [v.get("name") or v.get("login") for v in field_value if isinstance(v, dict) and (v.get("name") or v.get("login"))]
                             if names:
                                 cf_entry["value"] = ", ".join(names)
                             else:
                                 cf_entry["value"] = str(field_value) # Fallback to string representation
                        else:
                            # Handle simple values (string, number, date)
                            cf_entry["value"] = field_value

                        # --- DEBUG LOG --- #
                        logger.debug(f"Issue {base_details['idReadable']}: Found CF '{field_name}' = '{cf_entry['value']}' (Raw Value: {field_value})")
                        # --- END DEBUG LOG ---

                        custom_fields_data.append(cf_entry)

                        # --- Specific Assignee Handling ---
                        # Check for the CORRECT field name (plural)
                        if field_name == "Assignees": 
                            # --- DEBUG LOG (Re-enabled) --- #
                            logger.debug(f"Issue {base_details['idReadable']}: Processing Assignees field. Raw Value: {field_value}")
                            # --- END DEBUG LOG ---
                            if isinstance(field_value, dict):
                                # Single assignee (User type)
                                login_name = field_value.get("login") or field_value.get("name") # Prefer login, fallback to name
                                if login_name:
                                    assignee_name = login_name
                                    logger.debug(f"Issue {base_details['idReadable']}: Assignee set to '{assignee_name}' (from dict)") # DEBUG
                            elif isinstance(field_value, list) and field_value:
                                # Multiple assignees (potentially)
                                logins = [u.get("login") or u.get("name") for u in field_value if isinstance(u, dict) and (u.get("login") or u.get("name"))]
                                if logins:
                                     assignee_name = ", ".join(logins)
                                     logger.debug(f"Issue {base_details['idReadable']}: Assignee set to '{assignee_name}' (from list)") # DEBUG
                                # If list is empty or contains non-dict items, default remains Unassigned
                            # If field_value is None or not dict/list, default remains Unassigned
                            else:
                                logger.debug(f"Issue {base_details['idReadable']}: Assignee value is None or not dict/list. Keeping Unassigned.") # DEBUG

            # Add Assignee to base details
            base_details["Assignees"] = assignee_name # Changed field name to plural for consistency
            issues_data.append(base_details)

        issues_df = pd.DataFrame(issues_data)
        custom_fields_df = pd.DataFrame(custom_fields_data)

        # --- DEBUG LOG: Check columns after initial DF creation ---
        logger.debug(f"Initial issues_df columns: {issues_df.columns.tolist()}")
        # --- END DEBUG LOG ---

        # Convert timestamp columns
        for col in ['created', 'updated', 'resolved']:
            if col in issues_df.columns:
                issues_df[col] = pd.to_datetime(issues_df[col], unit='ms', errors='coerce')

        # Merge essential custom fields (State, Priority) into issues_df
        essential_fields_to_merge = ['State', 'Priority'] # Add others if needed
        for field_name in essential_fields_to_merge:
            if not custom_fields_df.empty:
                field_df = custom_fields_df[custom_fields_df['field_name'] == field_name][['issue_id', 'value']].rename(columns={'value': field_name})
                # Handle potential duplicate issue_id entries if a field somehow appears twice (take first)
                field_df = field_df.drop_duplicates(subset='issue_id', keep='first') 
                if not field_df.empty:
                    # Use 'id' from issues_df which matches 'issue_id' from custom_fields_df perspective
                    issues_df = pd.merge(issues_df, field_df, left_on='id', right_on='issue_id', how='left')
                    # Drop the redundant issue_id column from the merge
                    if 'issue_id' in issues_df.columns:
                         issues_df.drop(columns=['issue_id'], inplace=True)
                    logger.info(f"Merged '{field_name}' into issues_df.")
                else:
                    logger.warning(f"No data found for essential custom field '{field_name}' to merge.")
                    issues_df[field_name] = None # Add column with None if field doesn't exist
            else:
                 logger.warning(f"Custom fields dataframe is empty, cannot merge '{field_name}'.")
                 issues_df[field_name] = None
                 
        # Add readable ID column if not present (should be now)
        if 'idReadable' not in issues_df.columns and 'issue_readable_id' in custom_fields_df.columns:
             readable_ids = custom_fields_df[['issue_id', 'issue_readable_id']].drop_duplicates(subset='issue_id')
             issues_df = pd.merge(issues_df, readable_ids, on='issue_id', how='left')
             
        # Rename for consistency
        if 'idReadable' not in issues_df.columns and 'issue_readable_id' in issues_df.columns:
            issues_df = issues_df.rename(columns={'issue_readable_id': 'idReadable'})

        # Basic validation
        required_cols = ['id', 'idReadable', 'summary', 'created']
        missing_cols = [col for col in required_cols if col not in issues_df.columns]
        if missing_cols:
            logger.warning(f"Issues DataFrame is missing critical columns: {missing_cols}")

        return issues_df, custom_fields_df

    def _calculate_overall_metrics(self):
        """Calculates overall metrics like stale count and assignee workload from the issues_df."""
        if self.issues_df is None or self.issues_df.empty:
            logger.warning("Issues DataFrame is empty, cannot calculate overall metrics.")
            self.metrics_overall = {'stale_30d_count': 0, 'assignee_workload': {}}
            return
            
        # --- Stale Count --- 
        stale_count = 0
        if 'resolved' in self.issues_df.columns and 'created' in self.issues_df.columns:
            open_issues = self.issues_df[self.issues_df['resolved'].isna()].copy()
            if 'created' in open_issues.columns and pd.api.types.is_datetime64_any_dtype(open_issues['created']):
                 thirty_days_ago = datetime.now() - timedelta(days=30)
                 # Ensure compatible comparison (naive vs naive)
                 # Assuming 'created' is naive timezone, convert thirty_days_ago to naive
                 stale_issues = open_issues[open_issues['created'] < thirty_days_ago.replace(tzinfo=None)]
                 stale_count = len(stale_issues)
            else:
                 logger.warning("Cannot calculate stale count: 'created' column missing or not datetime.")
        else:
             logger.warning("Cannot calculate stale count: 'resolved' or 'created' columns missing.")
        
        # --- Assignee Workload --- 
        assignee_workload = {}
        if 'Assignees' in self.issues_df.columns and 'resolved' in self.issues_df.columns:
            open_issues = self.issues_df[self.issues_df['resolved'].isna()]
            # Use 'Unassigned' as the fill value consistently
            assignee_counts = open_issues['Assignees'].fillna('Unassigned').value_counts()
            assignee_workload = assignee_counts.to_dict()
            # No need to check for 'None' separately if 'Unassigned' is used consistently
        else:
             logger.warning("Cannot calculate assignee workload: 'Assignees' or 'resolved' columns missing.")
             
        self.metrics_overall = {
            'stale_30d_count': stale_count,
            'assignee_workload': assignee_workload
        }
        logger.info(f"Calculated overall metrics: Stale(>30d)={stale_count}, Workload Summary={assignee_workload}")

    def _process_activities(self):
        """Processes raw activities to calculate 24h metrics and create a recent activity DataFrame."""
        if not self.activities_raw:
            logger.warning("No raw activities found to process.")
            self.metrics_24h = {'created': 0, 'resolved': 0, 'new_blockers': 0, 'new_critical': 0}
            self.recent_activity_df = pd.DataFrame()
            return

        processed_activities = []
        created_24h = 0
        resolved_24h = 0
        new_blockers_24h = 0
        new_critical_24h = 0

        now = datetime.now()
        cutoff_time_24h = now - timedelta(hours=24)
        cutoff_timestamp_ms = int(cutoff_time_24h.timestamp() * 1000)

        # Get list of resolved state names
        resolved_state_names = []
        if self.custom_field_values and 'State' in self.custom_field_values:
             # Assuming State values have 'name' and potentially 'isResolved' flag, 
             # or rely on common names if flag unavailable
             common_resolved_names = ['Done', 'Resolved', 'Verified', 'Closed', 'Obsolete', 'Duplicate']
             resolved_state_names = [v.get('name') for v in self.custom_field_values['State'] 
                                     if v.get('name') in common_resolved_names] # Or use an isResolved flag if available
        if not resolved_state_names:
             logger.warning("Could not determine resolved state names from custom field values. Using defaults.")
             resolved_state_names = ['Done', 'Resolved', 'Verified', 'Closed', 'Obsolete', 'Duplicate']
        logger.info(f"Identified resolved states: {resolved_state_names}")

        # Define Blocker/Critical criteria
        blocker_priority_name = 'Critical' 
        blocker_state_name = 'Blocked' 
        critical_priority_name = 'Critical' # Can be same as blocker or different

        for activity in self.activities_raw:
            timestamp_ms = activity.get('timestamp')
            if not timestamp_ms:
                continue

            # Basic processing for DataFrame
            category = activity.get('category', {}).get('id', '')
            author = activity.get('author', {}).get('name', activity.get('author', {}).get('login', 'N/A'))
            target = activity.get('target', {})
            issue_id = target.get('id') if target.get('$type') == 'Issue' else None
            issue_readable_id = target.get('idReadable') if issue_id else None
            field = activity.get('field', {})
            field_name = field.get('name')
            added_obj = activity.get('added')
            removed_obj = activity.get('removed')
            
            # Simplify added/removed for logging/df
            def simplify_value(value_obj):
                if isinstance(value_obj, dict): return value_obj.get('name', value_obj.get('text', value_obj.get('presentation', str(value_obj))))
                if isinstance(value_obj, list): return ", ".join([simplify_value(v) for v in value_obj])
                return str(value_obj) if value_obj is not None else None
                
            added_simple = simplify_value(added_obj)
            removed_simple = simplify_value(removed_obj)

            processed_activities.append({
                'activity_id': activity.get('id'),
                'timestamp_ms': timestamp_ms,
                'category': category,
                'author': author,
                'issue_id': issue_id,
                'issue_readable_id': issue_readable_id,
                'field_name': field_name,
                'added_value': added_simple,
                'removed_value': removed_simple
            })

            # --- Calculate 24h Metrics --- 
            if timestamp_ms >= cutoff_timestamp_ms:
                if category == 'IssueCreatedCategory':
                    created_24h += 1
                elif category == 'CustomFieldCategory' and field_name == 'State':
                    added_state = added_simple
                    removed_state = removed_simple
                    # Check if it moved TO a resolved state FROM a non-resolved state
                    if added_state in resolved_state_names and (removed_state is None or removed_state not in resolved_state_names):
                        resolved_24h += 1
                    # Check if it moved TO a blocker state FROM non-blocker
                    if added_state == blocker_state_name and (removed_state is None or removed_state != blocker_state_name):
                         new_blockers_24h += 1
                         
                elif category == 'CustomFieldCategory' and field_name == 'Priority':
                     added_priority = added_simple
                     removed_priority = removed_simple
                     # Check if priority was changed TO blocker priority FROM non-blocker
                     if added_priority == blocker_priority_name and (removed_priority is None or removed_priority != blocker_priority_name):
                          new_blockers_24h += 1 
                     # Check if priority was changed TO CRITICAL priority FROM non-critical
                     if added_priority == critical_priority_name and (removed_priority is None or removed_priority != critical_priority_name):
                          new_critical_24h += 1 # Track newly critical

        self.metrics_24h = {
            'created': created_24h,
            'resolved': resolved_24h,
            'new_blockers': new_blockers_24h,
            'new_critical': new_critical_24h
        }
        logger.info(f"Calculated 24h metrics: {self.metrics_24h}")

        # Create DataFrame from processed activities
        self.recent_activity_df = pd.DataFrame(processed_activities)
        if not self.recent_activity_df.empty:
             self.recent_activity_df['timestamp'] = pd.to_datetime(self.recent_activity_df['timestamp_ms'], unit='ms', errors='coerce')
             logger.info(f"Created recent_activity_df with {len(self.recent_activity_df)} entries.")
        else:
             logger.info("No activities processed, recent_activity_df is empty.")

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
        """Process raw data into structured dataframes and calculate metrics."""
        if not self.raw_data:
            logger.error("No raw data loaded. Cannot process.")
            return False
        
        issues = self.raw_data.get('issues', [])
        # issue_histories = self.raw_data.get('issue_histories', {}) # Deprecated by activities
        sprints_data = self.raw_data.get('sprints', []) # If fetched separately

        try:
            # 1. Create Issues and Custom Fields DataFrames
            logger.info("Creating Issues and Custom Fields DataFrames...")
            self.issues_df, self.custom_fields_df = self._create_issues_dataframe(issues)
            if self.issues_df.empty:
                 logger.error("Issues DataFrame creation failed or resulted in empty data.")
                 return False
            logger.info(f"Issues DataFrame created with {len(self.issues_df)} rows.")
            if not self.custom_fields_df.empty:
                 logger.info(f"Custom Fields DataFrame created with {len(self.custom_fields_df)} rows.")
            else: 
                 logger.warning("Custom Fields DataFrame is empty.")

            # 2. Extract Comments
            logger.info("Extracting Comments...")
            self.comments_df = self._extract_comments(issues)
            if not self.comments_df.empty:
                logger.info(f"Comments DataFrame created with {len(self.comments_df)} rows.")
            else:
                 logger.info("No comments found or extracted.")

            # 3. Process Activities (Calculates 24h metrics)
            logger.info("Processing Activities...")
            self._process_activities()

            # 4. Calculate Overall Metrics (Stale count, workload)
            logger.info("Calculating Overall Metrics...")
            self._calculate_overall_metrics()

            # 5. Extract Sprint Data
            logger.info("Extracting Sprint Data...")
            # Use issues data, but also ensure sprints from raw_data root are included
            self.sprint_df = self._extract_sprint_data(issues)
            if not self.sprint_df.empty:
                logger.info(f"Sprint DataFrame created with {len(self.sprint_df)} rows.")
            else:
                 logger.info("No sprint data found or extracted.")

            # 6. Data Cleaning and Type Conversion (consolidated)
            logger.info("Performing final data cleaning and type conversions...")
            self._clean_and_convert_types()
            
            # 7. Save Processed Data
            self._save_processed_data()
            return True

        except Exception as e:
            logger.error(f"An error occurred during data processing: {e}", exc_info=True)
            return False
            
    def _clean_and_convert_types(self):
         """Centralized function for cleaning data and converting types across dataframes."""
         logger.info("Cleaning data and converting types...")
         # Issues DF (timestamps already handled in _create_issues_dataframe)
         # Convert relevant columns to numeric if applicable (use errors='coerce')
         
         # Comments DF
         if self.comments_df is not None and not self.comments_df.empty:
             if 'created' in self.comments_df.columns:
                 self.comments_df['created'] = pd.to_datetime(self.comments_df['created'], unit='ms', errors='coerce')
                 
         # Recent Activity DF
         if self.recent_activity_df is not None and not self.recent_activity_df.empty:
             # Timestamp handled in _process_activities
             pass # Add other conversions if needed
             
         # Sprint DF
         if self.sprint_df is not None and not self.sprint_df.empty:
             for col in ['sprint_start', 'sprint_finish']:
                 if col in self.sprint_df.columns:
                     self.sprint_df[col] = pd.to_datetime(self.sprint_df[col], unit='ms', errors='coerce')
         logger.info("Data cleaning and type conversion complete.")

    def _save_processed_data(self):
        """Saves the processed dataframes to a JSON file."""
        # ... (ensure directory exists) ...
        processed_output = {
            'issues': self.issues_df.to_dict(orient='records') if self.issues_df is not None else [],
            'custom_fields': self.custom_fields_df.to_dict(orient='records') if self.custom_fields_df is not None else [],
            'comments': self.comments_df.to_dict(orient='records') if self.comments_df is not None else [],
            'sprints': self.sprint_df.to_dict(orient='records') if self.sprint_df is not None else [],
            'recent_activities': self.recent_activity_df.to_dict(orient='records') if self.recent_activity_df is not None else [], # Add activities
            'metrics_24h': self.metrics_24h, # Add metrics
            'metrics_overall': self.metrics_overall, # Add overall metrics
            'custom_field_definitions': self.custom_field_values, # Add definitions
            'processing_timestamp': datetime.now().isoformat()
        }
        
        try:
            # --- Add Log Before --- #
            logger.info(f"Attempting to save processed data to {self.processed_data_path}")
            with open(self.processed_data_path, 'w', encoding='utf-8') as f:
                json.dump(processed_output, f, indent=2, default=str, ensure_ascii=False) # Use default=str for datetime, ensure_ascii=False for unicode
            # --- Add Log After --- #
            logger.info(f"Successfully completed writing processed data to {self.processed_data_path}")
        except Exception as e:
            logger.error(f"Error saving processed data to {self.processed_data_path}: {e}", exc_info=True)

    def get_status_transitions(self) -> pd.DataFrame:
        """Get status transitions from history data."""
        if self.recent_activity_df is None or self.recent_activity_df.empty:
            logger.warning("Recent activity data not available. Call process_data() first.")
            return pd.DataFrame()
            
        # Check if the required column exists
        if 'field_name' not in self.recent_activity_df.columns:
            logger.warning("field_name column not found in recent activity data. Creating empty dataframe.")
            # Create an empty dataframe with the expected columns
            return pd.DataFrame(columns=['issue_id', 'activity_id', 'timestamp', 
                                        'author', 'field_name', 'field_type', 
                                        'category', 'added_value', 'removed_value'])
        
        # Filter for 'State' field changes
        status_changes = self.recent_activity_df[self.recent_activity_df['field_name'] == 'State'].copy()
        
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
        if self.recent_activity_df is None or self.recent_activity_df.empty:
            logger.warning("Recent activity data not available. Call process_data() first.")
            return pd.DataFrame()
            
        # Check if the required column exists
        if 'field_name' not in self.recent_activity_df.columns:
            logger.warning("field_name column not found in recent activity data. Creating empty dataframe.")
            # Create an empty dataframe with the expected columns
            return pd.DataFrame(columns=['issue_id', 'activity_id', 'timestamp', 
                                        'author', 'field_name', 'field_type', 
                                        'category', 'added_value', 'removed_value'])
        
        # Filter for 'Assignee' field changes
        assignee_changes = self.recent_activity_df[self.recent_activity_df['field_name'] == 'Assignee'].copy()
        
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
