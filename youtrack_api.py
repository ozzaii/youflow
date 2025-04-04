"""
Module for interacting with the YouTrack API using the latest REST API.
"""
import os
import json
import logging
import time
import asyncio
import aiohttp
import requests
from urllib.parse import quote, urlencode
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from config import youtrack_config, app_config

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Dictionary mapping desired field names to potential YouTrack bundle names
CUSTOM_FIELD_BUNDLE_NAMES = {
    "State": "States",  # Updated from "State"
    "Priority": "Priorities",  # Updated from "Priority"
    "Type": "Types"  # Updated from "Type"
}

class YouTrackAPI:
    """Class for interacting with the latest YouTrack REST API."""
    
    def __init__(self):
        self.base_url = youtrack_config.base_url
        self.token = youtrack_config.token
        self.project_id = youtrack_config.project_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API response and check for errors."""
        if response.status_code in (200, 201):
            return response.json()
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', youtrack_config.retry_delay))
            logger.warning(f"Rate limited. Waiting for {retry_after} seconds.")
            time.sleep(retry_after)
            return {}  # Return empty dict instead of None
        else:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            response.raise_for_status()
            return {}  # This will only execute if raise_for_status doesn't raise an exception
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None, 
                     method: str = "GET", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a request to the YouTrack API with retries."""
        url = f"{self.base_url}/api/{endpoint}"
        
        for attempt in range(youtrack_config.max_retries):
            try:
                if method == "GET":
                    response = self.session.get(url, params=params, timeout=youtrack_config.timeout)
                elif method == "POST":
                    response = self.session.post(url, params=params, json=data, timeout=youtrack_config.timeout)
                elif method == "PUT":
                    response = self.session.put(url, params=params, json=data, timeout=youtrack_config.timeout)
                elif method == "DELETE":
                    response = self.session.delete(url, params=params, timeout=youtrack_config.timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                result = self._handle_response(response)
                if result is not None:
                    return result
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed (attempt {attempt+1}/{youtrack_config.max_retries}): {str(e)}")
                if attempt < youtrack_config.max_retries - 1:
                    time.sleep(youtrack_config.retry_delay)
                else:
                    raise
        
        return {}
    
    def list_all_projects(self) -> List[Dict[str, Any]]:
        """List all available projects on the YouTrack instance."""
        endpoint = "admin/projects"
        projects = self._make_request(endpoint)
        # Ensure we return a list even if the API returns a dict
        if isinstance(projects, dict):
            return [projects] if projects else []
        return projects if projects else []
    
    def get_project_details(self) -> Dict[str, Any]:
        """Get project details by ID or name."""
        # First try by project ID (shorter form)
        try:
            # Try to get project by ID first
            endpoint = f"admin/projects/{self.project_id}"
            return self._make_request(endpoint)
        except requests.exceptions.HTTPError:
            # If that fails, try URL-encoded full name
            logger.info(f"Project not found by ID, trying by name: {self.project_id}")
            encoded_project_id = quote(self.project_id, safe='')
            endpoint = f"admin/projects/{encoded_project_id}"
            return self._make_request(endpoint)
    
    def get_project_issues(self, fields: Optional[List[str]] = None, optimize_data: bool = True) -> List[Dict[str, Any]]:
        """
        Get all issues for the project with specified fields using the latest API.
        Returns ONLY the list of issues.
        """
        # Define minimal fields for closed/resolved issues to optimize token usage
        closed_issue_fields = [
            "id", "idReadable", "summary", "created", "updated", "resolved", 
            "assignee(id,name,login)",  # Try adding login, similar to base_fields
            "project(id)",  # Just project ID since we know which project we're working with
            "customFields(id,name,value(name))",  # Basic custom fields for status/priority
            "timeTracking(spentTime)"  # Total time spent for velocity analysis
        ]
        
        # Define base fields for all issues (used when optimization is disabled)
        base_fields = [
            "id", "idReadable", "summary", "created", "updated", "resolved", 
            "assignee(id,name,login)",
            "reporter(id,name)",
            "project(id,name,shortName)",
            "customFields(id,name,value(name))",  # Basic custom fields for status/priority
            "timeTracking(spentTime)",  # Total time spent for velocity analysis
            "tags(id,name)"  # Tags for categorization
        ]
        
        # Define detailed fields for open/active issues (comprehensive data)
        detail_fields = [
            "customFields(id,name,value(id,name,login,text,localizedName,presentation))",  # All custom field details
            "reporter(id,name,login,email,ringId)",  # Full reporter details
            "assignee(id,name,login,email,ringId)",  # Full assignee details
            "comments(id,text,created,author(id,name,login,email,ringId))",  # Full comment history
            "links(id,linkType(id,name,sourceToTarget,targetToSource),direction,issues(id,idReadable,summary))",  # Relationships
            "subtasks(id,idReadable,summary,resolved)",  # Subtask relationships
            "parent(id,idReadable,summary)",  # Parent relationship
            "sprint(id,name,goal,start,finish)",  # Sprint associations
            "timeTracking(workItems(id,date,duration,author(id,name,login,email)))"  # Detailed time tracking
        ]
        
        # If fields are explicitly specified, use those instead of our optimization
        if fields is not None:
            return self._get_issues_by_query(f"project: {self.project_id}", ",".join(fields))
            
        # If optimization is disabled, get full data for all issues
        if not optimize_data:
            complete_fields = base_fields + [
                field for field in detail_fields if field not in base_fields
            ]
            return self._get_issues_by_query(f"project: {self.project_id}", ",".join(complete_fields))
        
        # Use the optimized strategy - different field sets for open vs closed issues
        try:
            # First, get all open issues with complete data
            logger.info("Fetching all open issues with complete data...")
            # Use actual states identified from data analysis AND exclude SWINT
            open_issues_query = f"project: {self.project_id} State: -Done State: -Duplicate State: -Obsolete Subsystem: -SWINT"
            open_fields = base_fields + [
                field for field in detail_fields if field not in base_fields
            ]
            open_issues = self._get_issues_by_query(open_issues_query, ",".join(open_fields))
            logger.info(f"Found {len(open_issues)} open issues with full data (excluding SWINT)")
            
            # Then, get all closed issues with minimal data to optimize token usage
            logger.info("Fetching closed issues with minimal data...")
            # Use actual states identified from data analysis AND exclude SWINT
            closed_issues_query = f"project: {self.project_id} (State: Done OR State: Duplicate OR State: Obsolete) Subsystem: -SWINT"
            closed_issues = self._get_issues_by_query(closed_issues_query, ",".join(closed_issue_fields))
            logger.info(f"Found {len(closed_issues)} closed issues with minimal data (excluding SWINT)")
            
            # Combine both sets of issues
            all_issues = open_issues + closed_issues
            logger.info(f"Retrieved {len(all_issues)} total issues using optimized strategy (excluding SWINT)")
            return all_issues # Return the combined list
            
        except Exception as e:
            logger.error(f"Error fetching issues with optimized strategy: {str(e)}", exc_info=True)
            logger.info("Falling back to standard issue fetch method (excluding SWINT)...")
            # Define base fields if falling back
            base_fields = [
                "id", "idReadable", "summary", "created", "updated", "resolved",
                "reporter(id,name,login)",
                "project(id,name,shortName)",
                "tags(id,name)",
                # Ensure crucial custom fields are included even in fallback
                "customFields(id,name,value(id,name,login,presentation,text))"
            ]
            # ADDED Subsystem filter to fallback query
            fallback_query = f"project: {self.project_id} Subsystem: -SWINT"
            return self._get_issues_by_query(fallback_query, ",".join(base_fields))
    
    def _get_issues_by_query(self, query: str, field_param: str) -> List[Dict[str, Any]]:
        """
        Get issues matching a query with the specified fields, handling pagination.
        
        Args:
            query: YouTrack query string
            field_param: Comma-separated list of fields to include
            
        Returns:
            List of issue dictionaries
        """
        params = {
            "fields": field_param,
            "query": query,
            "$top": app_config.page_size
        }
        
        all_issues = []
        skip = 0
        
        while True:
            params["$skip"] = skip
            chunk = self._make_request("issues", params=params)
            
            if not chunk:
                break
                
            all_issues.extend(chunk)
            
            if len(chunk) < app_config.page_size:
                break
                
            skip += app_config.page_size
            logger.info(f"Retrieved {len(all_issues)} issues so far...")
        
        return all_issues
    
    def get_issue_details(self, issue_id: str, fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get detailed information for a specific issue."""
        if fields is None:
            # Simplified fields to reduce risk of API errors
            fields = [
                "id", "idReadable", "summary", "description", "created", "updated", "resolved", 
                "customFields(id,name)", 
                "assignee(id,name)",
                "reporter(id,name)",
                "project(id,name)"
            ]
        
        field_param = ",".join(fields)
        
        params = {
            "fields": field_param
        }
        
        endpoint = f"issues/{issue_id}"
        return self._make_request(endpoint, params=params)
    
    def get_issue_history(self, issue_id: str) -> List[Dict[str, Any]]:
        """Get the history of changes for a specific issue."""
        endpoint = f"issues/{issue_id}/activities"
        params = {
            "fields": "id,timestamp,author(id,name),category(id),added(id,name),removed(id,name),target(id,field(id,name))",
            "$top": 100
        }
        
        all_activities = []
        skip = 0
        
        while True:
            params["$skip"] = skip
            chunk = self._make_request(endpoint, params=params)
            
            if not chunk:
                break
                
            all_activities.extend(chunk)
            
            if len(chunk) < 100:
                break
                
            skip += 100
        
        return all_activities
    
    async def get_all_issue_histories_async(self, issue_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Get history for multiple issues asynchronously using the latest API."""
        async def fetch_history(session, issue_id):
            url = f"{self.base_url}/api/issues/{issue_id}/activities"
            params = {
                "fields": "id,timestamp,author(login),field(id,name),added(id,name),removed(id,name)",
                "categories": "CustomFieldCategory",
                "$top": 1000 # Fetch up to 1000 history items per issue
            }
            
            all_activities = []
            skip = 0
            
            try:
                while True:
                    params_with_skip = params.copy()
                    params_with_skip["$skip"] = skip
                    
                    for attempt in range(youtrack_config.max_retries):
                        try:
                            async with session.get(url, params=params_with_skip, 
                                                timeout=youtrack_config.timeout) as response:
                                if response.status == 200:
                                    chunk = await response.json()
                                    all_activities.extend(chunk)
                                    
                                    if len(chunk) < 1000:
                                        return issue_id, all_activities
                                        
                                    skip += 1000
                                    break
                                elif response.status == 429:
                                    retry_after = int(response.headers.get('Retry-After', youtrack_config.retry_delay))
                                    logger.warning(f"Rate limited for issue {issue_id}. Waiting for {retry_after} seconds.")
                                    await asyncio.sleep(retry_after)
                                elif response.status == 404:
                                    # Issue might have been deleted or is not accessible
                                    logger.warning(f"Issue {issue_id} not found or not accessible")
                                    return issue_id, []
                                elif response.status >= 500:
                                    # Server error - retry
                                    text = await response.text()
                                    logger.error(f"Server error for issue {issue_id}: {response.status} - {text}")
                                    if attempt == youtrack_config.max_retries - 1:
                                        return issue_id, []
                                    await asyncio.sleep(youtrack_config.retry_delay * (attempt + 1))  # Exponential backoff
                                else:
                                    text = await response.text()
                                    logger.error(f"API request failed for issue {issue_id}: {response.status} - {text}")
                                    if attempt == youtrack_config.max_retries - 1:
                                        return issue_id, []
                                    await asyncio.sleep(youtrack_config.retry_delay)
                        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                            logger.error(f"Request failed for issue {issue_id} (attempt {attempt+1}/{youtrack_config.max_retries}): {str(e)}")
                            if attempt == youtrack_config.max_retries - 1:
                                return issue_id, []
                            await asyncio.sleep(youtrack_config.retry_delay * (attempt + 1))  # Exponential backoff
            except Exception as e:
                # Catch any unexpected errors to avoid breaking the entire process
                logger.error(f"Unexpected error fetching history for issue {issue_id}: {str(e)}")
                return issue_id, []
            
            return issue_id, all_activities
        
        async with aiohttp.ClientSession(headers=self.headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
            tasks = []
            for issue_id in issue_ids:
                task = asyncio.ensure_future(fetch_history(session, issue_id))
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            
        return {issue_id: history for issue_id, history in results}
    
    def get_project_sprints(self) -> List[Dict[str, Any]]:
        """Get all sprints for the project."""
        # Try to find the agile board for this project
        endpoint = "agiles"
        params = {
            "fields": "id,name,projects(id,name)",
            "$top": 100
        }
        
        agiles = self._make_request(endpoint, params=params)
        # Ensure agiles is a list
        if isinstance(agiles, dict):
            agiles = [agiles] if agiles else []
        
        project_agile_id = None
        
        for agile in agiles:
            if not isinstance(agile, dict):
                continue
                
            projects = agile.get('projects', [])
            if isinstance(projects, dict):
                projects = [projects]
                
            for project in projects:
                if not isinstance(project, dict):
                    continue
                    
                # Match by project ID or name
                if project.get('id') == self.project_id or project.get('name') == self.project_id:
                    project_agile_id = agile.get('id')
                    break
            if project_agile_id:
                break
        
        if not project_agile_id:
            logger.warning(f"No agile board found for project: {self.project_id}")
            return []
        
        # Get sprints for this agile board
        endpoint = f"agiles/{project_agile_id}/sprints"
        params = {
            "fields": "id,name,goal,start,finish,status,isDefault",
            "$top": 100
        }
        
        sprints = self._make_request(endpoint, params=params)
        # Ensure sprints is a list
        if isinstance(sprints, dict):
            return [sprints] if sprints else []
        return sprints if sprints else []
    
    def get_custom_field_values(self, field_name: str) -> List[Dict[str, Any]]:
        """Get all possible values for a custom field."""
        # First get the custom field metadata
        endpoint = "admin/customFieldSettings/bundles"
        params = {
            "fields": "id,name,values(id,name,description,isResolved,ordinal)",
            "$top": 100
        }
        
        bundles = self._make_request(endpoint, params=params)
        # Ensure bundles is a list
        if isinstance(bundles, dict):
            bundles = [bundles] if bundles else []
        
        # Find the bundle that matches our field name
        for bundle in bundles:
            if not isinstance(bundle, dict):
                continue
                
            bundle_name = bundle.get('name', '')
            if isinstance(bundle_name, str) and bundle_name.lower() == field_name.lower():
                values = bundle.get('values', [])
                if isinstance(values, dict):
                    return [values] if values else []
                return values if values else []
        
        logger.warning(f"No custom field bundle found for field: {field_name}")
        return []

    def get_custom_field_bundle_values(self, field_name: str) -> List[Dict[str, Any]]:
        """Fetches all values for a named custom field bundle (e.g., 'State', 'Priority')."""
        # Use the mapping dictionary to get the correct bundle name
        bundle_name = CUSTOM_FIELD_BUNDLE_NAMES.get(field_name)
        if not bundle_name:
            logger.error(f"No bundle name mapping found for field: {field_name}")
            return []

        logger.info(f"Fetching values for custom field bundle: {field_name} (using YouTrack name: '{bundle_name}')")
        # First, we need to find the bundle ID for the given name.
        # This requires listing bundles and finding the match.
        # Assume common types: enum, state for now. Add others if needed.
        bundle_id = None
        bundle_type_found = None # Keep track of the type found
        for bundle_type in ['enum', 'state']:
            try:
                # Use _make_request for synchronous requests
                bundles_list = self._make_request(f"admin/customFieldSettings/bundles/{bundle_type}", params={"fields": "id,name"})
                if not isinstance(bundles_list, list): # Ensure it's a list
                    bundles_list = []

                for bundle in bundles_list:
                    # Log discovered bundle name and ID for debugging
                    discovered_name = bundle.get('name')
                    discovered_id = bundle.get('id')
                    if discovered_name and discovered_id:
                        logger.debug(f"Discovered bundle: Name='{discovered_name}', ID='{discovered_id}', Type='{bundle_type}'")

                    # Compare against the CORRECT bundle_name (plural)
                    # Make comparison robust: case-insensitive and strip whitespace
                    if discovered_name and bundle_name.strip().lower() == discovered_name.strip().lower():
                        bundle_id = bundle.get('id')
                        bundle_type_found = bundle_type # Store the type
                        logger.info(f"Found bundle ID '{bundle_id}' for name '{bundle_name}' (type: {bundle_type}) via robust comparison.") # Added robust marker
                        break
                if bundle_id:
                    break
            except Exception as e:
                logger.warning(f"Could not list bundles of type {bundle_type} to find '{bundle_name}': {e}")

        if not bundle_id or not bundle_type_found:
            logger.error(f"Could not find a bundle ID for name '{bundle_name}' used by field '{field_name}'. Cannot fetch values.")
            return []

        # Now fetch the values using the found bundle ID and type
        all_values = []
        skip = 0
        page_size = 100
        while True:
            params = {
                # Fetch relevant fields based on type
                "fields": "id,name,localizedName,presentation,ordinal,isArchived" + (",isResolved" if bundle_type_found == 'state' else ""),
                "$top": page_size,
                "$skip": skip
            }
            try:
                # Use _make_request for synchronous requests
                values_chunk = self._make_request(f"admin/customFieldSettings/bundles/{bundle_type_found}/{bundle_id}/values", params=params)
                if not values_chunk or not isinstance(values_chunk, list): # Ensure chunk is a list and not empty
                    break
                all_values.extend(values_chunk)
                if len(values_chunk) < page_size:
                    break
                skip += page_size
                logger.info(f"Fetched {len(all_values)} values for bundle '{bundle_name}' used by '{field_name}'...")
            except Exception as e:
                logger.error(f"Error fetching values for bundle '{bundle_name}' (ID: {bundle_id}): {e}")
                break

        logger.info(f"Retrieved {len(all_values)} values for bundle '{bundle_name}' (field: '{field_name}').")
        return all_values

    async def get_recent_issue_activities_async(self, issue_ids: List[str], 
                                                categories: Optional[List[str]] = None, 
                                                fields: Optional[str] = None,
                                                since_timestamp: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetches activities for a list of specific issues asynchronously using activitiesPage."""
        if fields is None:
            fields = "id,timestamp,author(login,name),target(id,idReadable,$type),category(id),field(id,name),added(id,name,login,text,presentation,minutes),removed(id,name,login,text,presentation,minutes)"
        
        all_activities = []
        
        async def fetch_activities_for_issue(session, issue_id):
            issue_activities = []
            cursor = None
            page_size = 100
            url = f"{self.base_url}/api/issues/{issue_id}/activitiesPage"
            
            while True:
                params = {
                    "fields": f"activities({fields}),afterCursor",
                    "$top": page_size
                }
                if categories:
                    params["categories"] = ",".join(categories)
                if cursor:
                    params["cursor"] = cursor
                
                try:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=youtrack_config.timeout)) as response:
                        if response.status == 200:
                            page_data = await response.json()
                            if not page_data or not page_data.get("activities"):
                                break # No more activities for this issue
                                
                            activities_chunk = page_data.get("activities", [])
                            
                            # Filter by timestamp if needed
                            if since_timestamp:
                                activities_chunk = [act for act in activities_chunk 
                                                    if act.get("timestamp") and act["timestamp"] >= since_timestamp]
                                                    
                            issue_activities.extend(activities_chunk)
                            cursor = page_data.get("afterCursor")
                            
                            if not cursor or len(activities_chunk) < page_size:
                                break # Last page for this issue
                                
                        elif response.status == 429:
                            retry_after = int(response.headers.get('Retry-After', youtrack_config.retry_delay))
                            logger.warning(f"Rate limited fetching activities for {issue_id}. Waiting {retry_after}s.")
                            await asyncio.sleep(retry_after)
                            # Continue loop to retry the same page
                        elif response.status == 404:
                             logger.warning(f"Issue {issue_id} not found when fetching activities.")
                             break # Issue likely deleted
                        else:
                            logger.error(f"Error {response.status} fetching activities for {issue_id}: {await response.text()}")
                            break # Stop trying for this issue on error
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Request failed fetching activities for {issue_id}: {e}")
                    break # Stop trying for this issue
            return issue_activities

        connector = aiohttp.TCPConnector(ssl=False) # Consider security implications
        async with aiohttp.ClientSession(headers=self.headers, connector=connector) as session:
            tasks = [fetch_activities_for_issue(session, issue_id) for issue_id in issue_ids]
            results = await asyncio.gather(*tasks)
            
            # Flatten the list of lists
            all_activities = [activity for sublist in results for activity in sublist]
            
        logger.info(f"Fetched a total of {len(all_activities)} activities for {len(issue_ids)} recent issues.")
        return all_activities

    def extract_full_project_data(self) -> Dict[str, Any]:
        """Extracts issues, recent activities for relevant issues, and custom field definitions."""
        logger.info(f"Starting data extraction for project: {self.project_id}")
        extracted_data = {
            "project_details": None,
            "agile_boards": [],
            "sprints": [],
            "issues": [],
            "activities": [],
            "custom_field_values": {}
        }
        
        try:
            # 1. Get Project Details
            extracted_data["project_details"] = self.get_project_details()
            logger.info(f"Retrieved project details: {extracted_data['project_details'].get('name', self.project_id)}")
            
            # 2. Get Agile Boards associated with the project (if applicable)
            try:
                all_boards = self._make_request("agiles", params={"fields": "id,name,projects(id)"})
                project_boards = [b for b in all_boards if any(p.get('id') == self.project_id for p in b.get('projects', []))]
                extracted_data["agile_boards"] = project_boards
                logger.info(f"Found {len(project_boards)} agile boards linked to project.")
                
                # 3. Get Sprints from linked boards
                for board in project_boards:
                    board_id = board.get('id')
                    sprints = self._make_request(f"agiles/{board_id}/sprints", params={"fields": "id,name,goal,start,finish,archived"})
                    extracted_data["sprints"].extend(sprints)
                logger.info(f"Retrieved {len(extracted_data['sprints'])} sprints from linked boards.")
                
            except Exception as agile_e:
                logger.warning(f"Could not retrieve agile board/sprint data (maybe none exist or API error): {agile_e}")
                # Proceed without agile data
                
            # 4. Get Issues (Using optimized strategy)
            all_issues = self.get_project_issues(optimize_data=True)
            extracted_data["issues"] = all_issues
            logger.info(f"Retrieved {len(extracted_data['issues'])} issues using optimized data strategy")
            
            # 5. Get Activities for RECENTLY UPDATED Issues
            if all_issues:
                 # Determine recent issues (e.g., updated in last 7 days)
                 recent_cutoff_time = datetime.now() - timedelta(days=7) # Look back 7 days
                 recent_cutoff_ts = int(recent_cutoff_time.timestamp() * 1000)
                 
                 recent_issue_ids = [issue['id'] for issue in all_issues 
                                       if issue.get('updated') and issue['updated'] >= recent_cutoff_ts]
                 
                 if recent_issue_ids:
                     logger.info(f"Found {len(recent_issue_ids)} issues updated recently. Fetching their activities...")
                     
                     # Define desired activity categories and fields
                     activity_categories = [
                         'IssueCreatedCategory', 
                         'IssueResolvedCategory', 
                         'CustomFieldCategory', # Captures changes to State, Priority etc.
                         'CommentAdded', 
                     ]
                     activity_fields = "id,timestamp,author(login,name),target(id,idReadable,$type),category(id),field(id,name),added(id,name,login,text,presentation,minutes),removed(id,name,login,text,presentation,minutes)"
                     
                     # Fetch activities asynchronously for recent issues
                     # Use a timestamp for the last 48 hours for the activity content itself
                     since_activity_time = datetime.now() - timedelta(hours=48)
                     since_activity_timestamp_ms = int(since_activity_time.timestamp() * 1000)
                     
                     # Run the async function
                     try:
                          extracted_data["activities"] = asyncio.run(
                              self.get_recent_issue_activities_async(
                                  issue_ids=recent_issue_ids,
                                  categories=activity_categories,
                                  fields=activity_fields,
                                  since_timestamp=since_activity_timestamp_ms
                              )
                          )
                          logger.info(f"Retrieved {len(extracted_data['activities'])} activities from recent issues.")
                     except RuntimeError as re:
                          # Handle cases where asyncio.run can't be called (e.g., already in an event loop)
                          logger.error(f"Could not run async activity fetch (RuntimeError): {re}. Consider integration if running within async context.")
                     except Exception as async_e:
                          logger.error(f"Error during async activity fetch: {async_e}", exc_info=True)
                 else:
                     logger.info("No issues found updated recently. Skipping activity fetch.")
            else:
                 logger.info("No issues found for the project. Skipping activity fetch.")
            
            # 6. Get Custom Field Values (States, Priorities) - Uses the corrected method above
            for field_name in CUSTOM_FIELD_BUNDLE_NAMES.keys(): # Iterate using keys from the dict
                 try:
                     # Call the corrected synchronous method
                     values = self.get_custom_field_bundle_values(field_name)
                     extracted_data["custom_field_values"][field_name] = values
                 except Exception as cf_e:
                     logger.error(f"Failed to get values for custom field '{field_name}': {cf_e}")

            # Save extracted data for debugging
            try:
                output_path = os.path.join('data', 'raw_youtrack_data.json')
                os.makedirs(os.path.dirname(output_path), exist_ok=True) # Ensure dir exists
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(extracted_data, f, indent=2, ensure_ascii=False, default=str)
                logger.info(f"Data extraction completed. Saved to {output_path}")
            except Exception as e:
                logger.error(f"Error saving raw extracted data: {e}")
                
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error extracting project data: {str(e)}", exc_info=True)
            raise

    async def _fetch_issues_page(self, query: str, fields: str, skip: int, top: int) -> List[Dict[str, Any]]:
        """Fetches a single page of issues asynchronously."""
        endpoint = f"{self.base_url}/api/issues"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        # REVERTED: No longer modifying fields here, rely on caller's field spec
        # if "Assignee" not in fields:
        #     fields += ",customFields(projectCustomField(field(name)),value(id,name,login))"

        params = {
            "query": query,
            "fields": fields, # Use fields as provided by the caller
            "$skip": skip,
            "$top": top
        }
        # Use the shared session
        try:
            # Assuming self.session is an aiohttp.ClientSession initialized elsewhere
            async with self.session.get(endpoint, headers=headers, params=params, timeout=self.timeout) as response:
                response.raise_for_status()
                return await response.json()
        except ClientResponseError as e:
            logger.error(f"HTTP error fetching issues page ({skip}-{skip+top}): {e.status} {e.message}", exc_info=True)
            return []
        except asyncio.TimeoutError:
            logger.error(f"Timeout error fetching issues page ({skip}-{skip+top})")
            return []
        except Exception as e:
            logger.error(f"Error fetching issues page ({skip}-{skip+top}): {e}", exc_info=True)
            return []
