#!/usr/bin/env python3

from youtrack_api import YouTrackAPI
import json
from typing import List, Dict, Any

def main():
    api = YouTrackAPI()
    print("Checking available projects...")
    
    # Try to get projects with more fields
    endpoint = "admin/projects"
    params = {
        "fields": "id,name,shortName,description,$type"
    }
    projects = api._make_request(endpoint, params=params)
    
    # Ensure projects is a list
    if isinstance(projects, dict):
        projects = [projects] if projects else []
    elif not isinstance(projects, list):
        projects = []
        
    print(f"Found {len(projects)} projects")
    
    print("\nProject details:")
    for p in projects:
        if not isinstance(p, dict):
            print("Invalid project data format")
            continue
        print(f"ID: {p.get('id', 'N/A')}")
        print(f"Name: {p.get('name', 'N/A')}")
        print(f"ShortName: {p.get('shortName', 'N/A')}")
        print(f"Description: {p.get('description', 'N/A')}")
        print("-" * 50)
    
    print("\nFull project data:")
    print(json.dumps(projects, indent=2))

if __name__ == "__main__":
    main()