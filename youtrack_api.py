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

from config import youtrack_config, app_config

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
            return None
        else:
            logger.error(f"API request failed: {response.status_code} - {response.text}")
            response.raise_for_status()
    
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
    
    def get_project_issues(self, fields: List[str] = None) -> List[Dict[str, Any]]:
        """Get all issues for the project with specified fields using the latest API."""
        if fields is None:
            fields = [
                "id", "idReadable", "summary", "description", "created", "updated", "resolved", 
                "customFields(id,name,value(id,name,text,localizedName,presentation))", 
                "tags(id,name,color(id,background,foreground))", 
                "comments(id,text,created,author(id,login,name,email))",
                "sprint(id,name,goal,start,finish)", 
                "assignee(id,login,name,email)",
                "reporter(id,login,name,email)",
                "voters(id,login,name,email)",
                "watchers(id,login,name,email)",
                "links(id,direction,linkType(id,name,sourceToTarget,targetToSource),issues(id,idReadable,summary))",
                "subtasks(id,idReadable,summary,resolved)",
                "parent(id,idReadable,summary)",
                "timeTracking(id,workItems(id,duration,date,author(id,login,name),text))",
                "project(id,name,shortName)"
            ]
        
        field_param = ",".join(fields)
        
        # Improved query to use project ID/shortname instead of full name for better compatibility
        project_query = f"project: {{{self.project_id}}}"
        
        params = {
            "fields": field_param,
            "query": project_query,
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
        
        logger.info(f"Retrieved {len(all_issues)} issues in total.")
        return all_issues
    
    def get_issue_details(self, issue_id: str, fields: List[str] = None) -> Dict[str, Any]:
        """Get detailed information for a specific issue."""
        if fields is None:
            fields = [
                "id", "idReadable", "summary", "description", "created", "updated", "resolved", 
                "customFields(id,name,value(id,name,text,localizedName,presentation))", 
                "tags(id,name,color(id,background,foreground))", 
                "comments(id,text,created,author(id,login,name,email))",
                "sprint(id,name,goal,start,finish)", 
                "assignee(id,login,name,email)",
                "reporter(id,login,name,email)",
                "voters(id,login,name,email)",
                "watchers(id,login,name,email)",
                "links(id,direction,linkType(id,name,sourceToTarget,targetToSource),issues(id,idReadable,summary))",
                "subtasks(id,idReadable,summary,resolved)",
                "parent(id,idReadable,summary)",
                "timeTracking(id,workItems(id,duration,date,author(id,login,name),text))",
                "project(id,name,shortName)"
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
            "fields": "id,timestamp,author(id,login,name),category(id),added(id,name,text),removed(id,name,text),target(id,field(id,name,customField(id,name,fieldType(id,name))))",
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
                "fields": "id,timestamp,author(id,login,name),category(id),added(id,name,text),removed(id,name,text),target(id,field(id,name,customField(id,name,fieldType(id,name))))",
                "$top": 100
            }
            headers = self.headers.copy()
            
            all_activities = []
            skip = 0
            
            while True:
                params_with_skip = params.copy()
                params_with_skip["$skip"] = skip
                
                for attempt in range(youtrack_config.max_retries):
                    try:
                        async with session.get(url, headers=headers, params=params_with_skip, 
                                              timeout=youtrack_config.timeout) as response:
                            if response.status == 200:
                                chunk = await response.json()
                                all_activities.extend(chunk)
                                
                                if len(chunk) < 100:
                                    return issue_id, all_activities
                                    
                                skip += 100
                                break
                            elif response.status == 429:
                                retry_after = int(response.headers.get('Retry-After', youtrack_config.retry_delay))
                                logger.warning(f"Rate limited for issue {issue_id}. Waiting for {retry_after} seconds.")
                                await asyncio.sleep(retry_after)
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
                        await asyncio.sleep(youtrack_config.retry_delay)
            
            return issue_id, all_activities
        
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_history(session, issue_id) for issue_id in issue_ids]
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
        project_agile_id = None
        
        for agile in agiles:
            for project in agile.get('projects', []):
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
        
        return self._make_request(endpoint, params=params)
    
    def get_custom_field_values(self, field_name: str) -> List[Dict[str, Any]]:
        """Get all possible values for a custom field."""
        # First get the custom field metadata
        endpoint = "admin/customFieldSettings/bundles"
        params = {
            "fields": "id,name,values(id,name,description,isResolved,ordinal)",
            "$top": 100
        }
        
        bundles = self._make_request(endpoint, params=params)
        
        # Find the bundle that matches our field name
        for bundle in bundles:
            if bundle.get('name', '').lower() == field_name.lower():
                return bundle.get('values', [])
        
        logger.warning(f"No custom field bundle found for field: {field_name}")
        return []
    
    def extract_full_project_data(self) -> Dict[str, Any]:
        """Extract complete data for the project including issues, histories, and sprints."""
        logger.info(f"Starting data extraction for project: {self.project_id}")
        
        try:
            # Get project details
            project_details = self.get_project_details()
            logger.info(f"Retrieved project details: {project_details.get('name', self.project_id)}")
            
            # Get all sprints for the project
            sprints = self.get_project_sprints()
            logger.info(f"Retrieved {len(sprints)} sprints")
            
            # Get all issues for the project
            issues = self.get_project_issues()
            logger.info(f"Retrieved {len(issues)} issues")
            
            # Get issue IDs
            issue_ids = [issue["id"] for issue in issues]
            
            # Get issue histories asynchronously
            if issue_ids:
                issue_histories = asyncio.run(self.get_all_issue_histories_async(issue_ids))
                logger.info(f"Retrieved history for {len(issue_histories)} issues")
            else:
                issue_histories = {}
            
            # Get custom field values for key fields
            custom_field_bundles = {
                "State": self.get_custom_field_values("State"),
                "Type": self.get_custom_field_values("Type"),
                "Priority": self.get_custom_field_values("Priority")
            }
            
            logger.info(f"Retrieved custom field values for {len(custom_field_bundles)} fields")
            
            # Combine the data
            project_data = {
                "project": project_details,
                "sprints": sprints,
                "issues": issues,
                "issue_histories": issue_histories,
                "custom_field_bundles": custom_field_bundles,
                "extraction_timestamp": time.time()
            }
            
            # Save to file
            output_path = os.path.join(app_config.data_dir, app_config.issues_file)
            with open(output_path, 'w') as f:
                json.dump(project_data, f, indent=2)
            
            logger.info(f"Data extraction completed. Saved to {output_path}")
            return project_data
            
        except Exception as e:
            logger.error(f"Error extracting project data: {str(e)}", exc_info=True)
            raise
