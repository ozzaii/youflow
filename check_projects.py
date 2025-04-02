#!/usr/bin/env python3

from youtrack_api import YouTrackAPI
import json

def main():
    api = YouTrackAPI()
    print("Checking available projects...")
    
    # Try to get projects with more fields
    endpoint = "admin/projects"
    params = {
        "fields": "id,name,shortName,description,$type"
    }
    projects = api._make_request(endpoint, params=params)
    print(f"Found {len(projects)} projects")
    
    print("\nProject details:")
    for p in projects:
        print(f"ID: {p.get('id', 'N/A')}")
        print(f"Name: {p.get('name', 'N/A')}")
        print(f"ShortName: {p.get('shortName', 'N/A')}")
        print(f"Description: {p.get('description', 'N/A')}")
        print("-" * 50)
    
    print("\nFull project data:")
    print(json.dumps(projects, indent=2))

if __name__ == "__main__":
    main()