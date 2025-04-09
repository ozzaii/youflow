import os
import logging
from datetime import datetime
import time
import tempfile

# Import project modules
import config
from youtrack_api import YouTrackAPI
from data_processor import DataProcessor
# Import the specific generator class and new methods
from ai_insights import AIInsightsGenerator
from voice_summary import generate_audio_summary, initialize_client as init_elevenlabs
# Import the new email body function
from email_reporter import create_leadership_email_body, send_email, load_recipients

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
PROJECT_ID = config.YOUTRACK_PROJECT_ID # Get project ID from config
DATA_DIR = "data"
RAW_DATA_FILE = os.path.join(DATA_DIR, "raw_youtrack_data.json")
PROCESSED_DATA_FILE = os.path.join(DATA_DIR, "processed_youtrack_data.json") # Or wherever processor saves

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

def main():
    """Main function to generate and send the daily report."""
    start_time = time.time()
    logging.info("Starting daily report generation process...")
    report_date = datetime.now().strftime("%Y-%m-%d")

    # --- 1. Fetch Data ---
    logging.info("Fetching latest data from YouTrack...")
    api = YouTrackAPI(config.YOUTRACK_BASE_URL, config.YOUTRACK_TOKEN, PROJECT_ID)
    try:
        raw_data = api.extract_full_project_data(save_path=RAW_DATA_FILE)
        if not raw_data:
            logging.error("Failed to fetch raw data from YouTrack. Aborting.")
            return
        logging.info(f"Raw data saved to {RAW_DATA_FILE}")
    except Exception as e:
        logging.error(f"Error fetching data from YouTrack: {e}")
        return

    # --- 2. Process Data ---
    logging.info("Processing YouTrack data...")
    processor = DataProcessor(RAW_DATA_FILE)
    try:
        processed_data = processor.process_data(save_path=PROCESSED_DATA_FILE)
        if processed_data is None:
             logging.error("Data processing failed. Aborting.")
             return
        issues_df = processed_data['issues']
        comments_df = processed_data['comments']
        history_df = processed_data['history']
        custom_fields_df = processed_data['custom_fields']
        logging.info(f"Data processed successfully. Output saved conceptually to {PROCESSED_DATA_FILE}")
    except Exception as e:
        logging.error(f"Error processing data: {e}")
        return

    # --- 3. Initialize AI Generator ---
    ai_generator = AIInsightsGenerator() # Use default model

    # --- 4. Generate Leadership Email Content ---
    logging.info("Generating structured AI content for email report...")
    email_content_dict = None
    try:
        email_content_dict = ai_generator.generate_leadership_email_content(processor)
        if email_content_dict and not email_content_dict.get('error'):
            logging.info("Successfully generated structured email content.")
        else:
            logging.error(f"Failed to generate structured email content: {email_content_dict.get('error', 'Unknown error')}")
            # Use default error content if generation fails
            email_content_dict = {
                "daily_pulse": "Error generating AI content.",
                "risk_intelligence": "Error generating AI content.",
                "team_performance": "Error generating AI content.",
                "activity_summary": "Error generating AI content."
            }
    except Exception as e:
        logging.error(f"Exception during email content generation: {e}", exc_info=True)
        email_content_dict = {
             "daily_pulse": f"Exception: {e}", "risk_intelligence": f"Exception: {e}",
             "team_performance": f"Exception: {e}", "activity_summary": f"Exception: {e}"
        }


    # --- 5. Generate Voice Summary Script ---
    logging.info("Attempting to generate AI voice script...")
    # Assuming 'ai_insights' contains the structured summary needed for the OLD voice script function
    # voice_script_text = ai_generator.generate_voice_summary_script(processor)
    # Commenting out the call to the old function
    voice_script_text = "# Voice script generation disabled in generate_daily_report.py"
    logging.info("Voice script generation (old method) is disabled in this script.")
    # Check if voice script generation failed (indicated by specific error string)

    # --- 6. Generate Audio File from Script ---
    audio_file_path = None
    if voice_script_text:
        logging.info("Generating voice summary audio file...")
        try:
            if init_elevenlabs(): # Check if client can be initialized (API key exists)
                 audio_file_path = generate_audio_summary(voice_script_text)
                 if audio_file_path:
                     logging.info(f"Voice summary audio generated: {audio_file_path}")
                 else:
                     logging.warning("Voice summary audio generation failed.")
            else:
                logging.warning("ElevenLabs client could not be initialized (check API key). Skipping voice audio generation.")
        except Exception as e:
            logging.error(f"Error generating voice summary audio: {e}")
    else:
        logging.info("Skipping voice audio generation as no script was generated.")


    # --- 7. Create Email Body ---
    logging.info("Creating email body...")
    project_name = raw_data.get('project_details', {}).get('name', PROJECT_ID)
    # Use the new function and the structured content
    subject, html_body = create_leadership_email_body(project_name, email_content_dict, report_date)

    # --- 8. Load Recipients ---
    logging.info("Loading recipients...")
    recipients = load_recipients()

    # --- 9. Send Email ---
    if recipients:
        logging.info(f"Sending email report to {len(recipients)} recipients...")
        success = send_email(subject, html_body, recipients, audio_attachment_path=audio_file_path)
        if success:
            logging.info("Email report sent successfully.")
        else:
            logging.error("Failed to send email report.")
    else:
        logging.warning("No recipients found. Skipping email sending.")

    # --- 10. Cleanup ---
    if audio_file_path and os.path.exists(audio_file_path):
        try:
            # Only remove if it's in the temp directory (as implemented in voice_summary)
            if audio_file_path.startswith(tempfile.gettempdir()):
                os.remove(audio_file_path)
                logging.info(f"Cleaned up temporary audio file: {audio_file_path}")
        except Exception as e:
            logging.warning(f"Could not clean up temporary audio file {audio_file_path}: {e}")


    end_time = time.time()
    logging.info(f"Daily report generation process finished in {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    main()
