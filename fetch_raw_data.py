import asyncio
import json
import logging
import os
from datetime import datetime

from youtrack_api import YouTrackAPI
from config import app_config, youtrack_config

# Configure logging (same as in youtrack_api.py)
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main function to fetch and save YouTrack data."""
    logger.info("Starting raw data fetch...")
    
    api = YouTrackAPI()
    
    try:
        # 1. Fetch issues using the (temporarily modified) optimized strategy
        logger.info("Fetching project issues...")
        issues = api.get_project_issues(optimize_data=True)
        logger.info(f"Fetched {len(issues)} issues.")
        
        # 2. Fetch issue histories asynchronously
        logger.info("Fetching issue histories...")
        issue_ids = [issue['id'] for issue in issues if 'id' in issue]
        if not issue_ids:
             logger.warning("No issue IDs found to fetch history for.")
             histories = {}
        else:
            histories = await api.get_all_issue_histories_async(issue_ids)
            logger.info(f"Fetched histories for {len(histories)} issues.")

        # 3. Combine results
        raw_data = {
            'issues': issues,
            'issue_histories': histories,
            'fetch_timestamp': datetime.now().isoformat(),
            'project_id': youtrack_config.project_id
        }
        
        # 4. Save to file
        output_dir = app_config.data_dir
        output_file = app_config.raw_data_file # Use config for filename
        output_path = os.path.join(output_dir, output_file)
        
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Saving raw data to {output_path}...")
        with open(output_path, 'w') as f:
            json.dump(raw_data, f, indent=2) # Use indent for readability
            
        logger.info("Raw data fetch and save completed successfully.")
        
    except Exception as e:
        logger.error(f"An error occurred during data fetch: {str(e)}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 