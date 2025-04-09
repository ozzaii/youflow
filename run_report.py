# run_report.py
import os
import logging
import sys
import time
import traceback
from datetime import datetime
from dotenv import load_dotenv
import re
import pandas as pd
import glob
import config

# --- Load .env variables early ---
load_dotenv()

# --- Logging Setup ---
from config import AppConfig
app_config = AppConfig()

# Configure logging
log_level_str = os.getenv('LOG_LEVEL', app_config.log_level).upper()
log_level = getattr(logging, log_level_str, logging.INFO)
print(f"Log Level: {log_level_str}") # Print effective log level

log_file_path = os.path.join('logs', 'reporter.log')
# Ensure logs directory exists
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

# Set root logger level back to configured level
logging.basicConfig(
    level=log_level, # <-- Set back to configured level (INFO or from .env)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),
        logging.StreamHandler() # Log to console as well
    ]
)

# Silence noisy libraries if needed
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

logger = logging.getLogger("ReportRunner")

# --- Configuration and API Setup ---
from config import youtrack_config # Keep for log level, AppConfig, and youtrack_config
# from config import YOUTRACK_BASE_URL, YOUTRACK_TOKEN, YOUTRACK_PROJECT_ID # REMOVED
from youtrack_api import YouTrackAPI
# --- Core Logic Modules ---
from data_processor import DataProcessor
from ai_insights import AIInsightsGenerator
from voice_generator import generate_voice_summary
from email_reporter import _load_recipients, send_email, create_leadership_email_body
from src.visualization import execute_plot_code # <-- Import the new function

# --- Constants ---
VOICE_SUMMARY_FILENAME = "data/daily_voice_summary.mp3"
REPORT_INTERVAL_SECONDS = 24 * 60 * 60 # 24 hours
# REPORT_INTERVAL_SECONDS = 60 # Short interval for testing

# --- Helper Functions ---
def create_voice_summary_text(insights: dict) -> str:
    """Creates a concise text summary suitable for voice synthesis from AI insights."""
    # Try to extract specific points first
    pulse = insights.get('daily_pulse', '')
    risks = insights.get('risk_intelligence', '')
    team = insights.get('team_performance', '')

    summary_parts = []
    health_found = False
    focus_found = False
    risk_found = False
    perf_found = False

    # Extract Health
    health_match = re.search(r"Project Health:\*\*\s*(.*?)(?:\n|\||$)", pulse, re.IGNORECASE)
    if health_match:
        summary_parts.append(f"Project health is {health_match.group(1).strip()}.")
        health_found = True

    # Extract Focus
    focus_match = re.search(r"Focus:\*\*\s*(.*?)(?:\n\n|\Z)", pulse, re.DOTALL | re.IGNORECASE)
    if focus_match:
        focus_text = focus_match.group(1).strip()
        focus_text = re.sub(r'^\s*\*\s*', '', focus_text, flags=re.MULTILINE) 
        focus_text = re.sub(r'\n\s*\*?\s*', '. ', focus_text)
        summary_parts.append(f"Key focus items: {focus_text}")
        focus_found = True

    # Extract Risks (Blockers/Bottlenecks)
    blocked_match = re.search(r"New Blockers:\*\*\s*(.*?)(?:\n|\Z)", risks, re.IGNORECASE)
    bottleneck_match = re.search(r"Bottlenecks:\*\*\s*(.*?)(?:\n|\Z)", risks, re.IGNORECASE)
    if blocked_match and blocked_match.group(1).strip() not in ['None', 'None identified', 'Data unavailable']:
        summary_parts.append(f"New blockers: {blocked_match.group(1).strip()}.")
        risk_found = True
    if bottleneck_match and bottleneck_match.group(1).strip() not in ['None', 'None identified', 'Data unavailable']:
        summary_parts.append(f"Potential bottlenecks: {bottleneck_match.group(1).strip()}.")
        risk_found = True
        
    # Extract Performance Highlight (Workload)
    workload_match = re.search(r"Workload:\*\*\s*(.*?)(?:\n|\||$)", team, re.IGNORECASE)
    if workload_match and workload_match.group(1).strip() not in ['None', 'None identified', 'Data unavailable']:
        summary_parts.append(f"Workload notes: {workload_match.group(1).strip()}.")
        perf_found = True

    # Fallback if specific points are missing
    if not health_found and pulse and 'Parsing Error' not in pulse:
         summary_parts.insert(0, pulse.split('\n')[0]) # Use first line of pulse if health missing
    if not focus_found and not risk_found and risks and 'Parsing Error' not in risks:
         summary_parts.append(risks.split('\n')[0]) # Use first line of risks if focus/risk specifics missing

    if not summary_parts:
        logger.warning("Could not extract any meaningful points for voice summary.")
        return "" # Return empty string if nothing found

    # Construct final summary
    full_summary = "Good morning. Here is your MQ EIS KG BSW daily briefing. " + " ... ".join(summary_parts)
    full_summary = re.sub(r'\s+', ' ', full_summary).strip()
    # Basic replacements for better speech
    full_summary = full_summary.replace('EISMMABSW-', 'E. I. S. M. M. A. B. S. W. dash ')
    logger.info(f"Created voice summary text (length: {len(full_summary)} chars)")
    return full_summary

def run_single_report_cycle(youtrack_api: YouTrackAPI):
    """Runs one complete cycle of fetching, processing, and reporting."""
    logger.info("--- Starting Single Report Cycle --- ")
    cycle_start_time = time.time()
    # Initialize success flag and attachment list
    success = False
    attachment_paths = []
    generated_plot_files = [] # <-- New list for locally generated plots

    try:
        # 1. Fetch Fresh Data
        logger.info("Step 1: Fetching fresh data from YouTrack...")
        raw_data = youtrack_api.extract_full_project_data()
        if not raw_data or not raw_data.get("issues"):
            logger.error("Failed to fetch valid data or issues from YouTrack. Aborting cycle.")
            return False # Indicate cycle failure
        logger.info(f"Successfully fetched fresh data. Found {len(raw_data.get('issues', []))} issues.")

        # 2. Process Data
        logger.info("Step 2: Processing YouTrack data...")
        processor = DataProcessor(raw_data_dict=raw_data)
        processor.process_data()
        if processor.issues_df is None or processor.issues_df.empty:
            logger.error("Data processing failed or resulted in empty dataframes. Aborting cycle.")
            return False
        logger.info("Data processing complete.")

        # 3. Generate AI Insights (Analysis Text and Plot Code Strings)
        logger.info("Step 3: Generating AI analysis and plot code...")
        ai_generator = AIInsightsGenerator()
        ai_results = ai_generator.generate_leadership_report_insights(processor)
        # ai_results now contains 'analysis_text', 'voice_script', 'plot_code_strings', 'error'

        analysis_error = ai_results.get("error")
        if analysis_error:
            logger.error(f"AI insight generation failed or partially failed: {analysis_error}. Proceeding with available data.")
            # Decide if error is critical - allow proceeding if some text was generated
            if not ai_results.get("analysis_text"):
                logger.critical(f"Stopping cycle due to critical error during insight generation: {analysis_error}")
                return False
        else:
            logger.info("AI analysis and plot code suggestions generated successfully.")

        # --- NEW: Step 3.5: Execute Generated Plot Code --- 
        plot_code_strings = ai_results.get("plot_code_strings", [])
        if plot_code_strings:
            logger.info(f"Attempting to execute {len(plot_code_strings)} generated plot code blocks...")
            # Prepare the data dictionary the AI code expects
            # IMPORTANT: Keys must match EXACTLY what was specified in the AI prompt
            plot_data = {
                'assignee_workload_dict': processor.metrics_overall.get('Workload Summary', {}), # Match key from data_processor
                'state_counts_dict': processor.metrics_overall.get('open_issue_state_counts', {}), # Calculate this if needed
                'recent_activity_metrics': processor.metrics_24h or {},
                'overall_metrics': processor.metrics_overall or {}
            }
            # Example: Add state counts if not directly in metrics_overall
            if 'state_counts_dict' not in plot_data or not plot_data['state_counts_dict']:
                 if processor.issues_df is not None and 'State' in processor.issues_df.columns:
                     open_issues_df = processor.issues_df[pd.isna(processor.issues_df['resolved'])].copy()
                     plot_data['state_counts_dict'] = open_issues_df['State'].fillna('Unknown').value_counts().to_dict()
                 else:
                     plot_data['state_counts_dict'] = {}

            # --- ADDED LOGGING --- 
            logger.info(f"--- Plot Data Prepared ---")
            logger.info(f"Assignee Workload Dict (len={len(plot_data.get('assignee_workload_dict', {}))}): {str(plot_data.get('assignee_workload_dict', {}))[:200]}...")
            logger.info(f"State Counts Dict (len={len(plot_data.get('state_counts_dict', {}))}): {str(plot_data.get('state_counts_dict', {}))[:200]}...")
            logger.info(f"Recent Activity Metrics: {plot_data.get('recent_activity_metrics', {})}")
            logger.info(f"Overall Metrics (keys): {list(plot_data.get('overall_metrics', {}).keys())}")
            # --- END LOGGING --- 

            for i, code in enumerate(plot_code_strings):
                logger.info(f"Executing plot code block {i+1}...")
                try:
                    # Call the execution function from visualization.py
                    plots_from_block = execute_plot_code(code, plot_data)
                    if plots_from_block:
                        generated_plot_files.extend(plots_from_block)
                        logger.info(f"Successfully generated plots: {plots_from_block}")
                    else:
                        logger.warning(f"Plot code block {i+1} executed but produced no plot files.")
                except Exception as exec_err: # Catch errors from execute_plot_code itself
                    logger.error(f"Critical error executing plot code block {i+1}: {exec_err}", exc_info=True)
                    # Decide whether to stop the whole cycle or just skip this plot
        else:
            logger.info("No plot code generated by AI.")
        
        # Add successfully generated plot files to attachments
        if generated_plot_files:
             attachment_paths.extend(generated_plot_files)
             logger.info(f"Added {len(generated_plot_files)} locally generated plot file(s) to attachments.")

        # 4. Generate Voice Summary AUDIO (Using the generated script)
        logger.info("Step 4: Generating voice summary AUDIO...")
        voice_script_text = ai_results.get("voice_script") # Use the script directly
        # --- ADDED LOGGING --- 
        logger.info(f"Attempting to generate voice for script (first 100 chars): {voice_script_text[:100]}...")
        if voice_script_text and "Error:" not in voice_script_text:
            try:
                voice_file_path = generate_voice_summary(voice_script_text, VOICE_SUMMARY_FILENAME)
                # --- ADDED LOGGING --- 
                logger.info(f"Voice generation function returned path: {voice_file_path}")
                if voice_file_path and os.path.exists(voice_file_path):
                    attachment_paths.append(voice_file_path) # Add reliably here
                    logger.info(f"Voice summary file exists and added to attachments: {voice_file_path}")
                else:
                    logger.error(f"Voice generation returned no path OR file not found at: {voice_file_path}")
            except Exception as voice_err:
                logger.error(f"Error during voice summary generation or saving: {voice_err}", exc_info=True)
        else:
            log_message = f"Voice script generation skipped or failed: {voice_script_text if voice_script_text else 'Not generated'}"
            logger.warning(log_message)

        # 5. Prepare and Send Email (Using the raw analysis text)
        logger.info("Step 5: Preparing and sending email report...")
        recipients = config.REPORT_RECIPIENTS # NEW: Use config list
        if not recipients:
            logger.error("No recipients found in config.py. Cannot send email report.")
            # Don't mark cycle as success if email can't be sent
        else:
            # Get the raw analysis text directly
            raw_analysis = ai_results.get("analysis_text")
            if not raw_analysis:
                logger.warning("Raw analysis text is missing from AI results, providing default message for email.")
                raw_analysis = "AI Analysis generation failed or returned empty. Please check logs."

            # <<< ADDED: Get Turkish analysis >>>
            turkish_analysis = ai_results.get("turkish_analysis")
            if not turkish_analysis or turkish_analysis.startswith("Hata:") or turkish_analysis.startswith("Çeviri Hatası:"):
                logger.warning(f"Turkish analysis missing or failed: {turkish_analysis}. Email will not include Turkish section.")
                turkish_analysis = None # Ensure it's None if failed/missing
            # <<< END ADDED >>>

            # Create email body using the raw analysis text and Turkish text
            email_body = create_leadership_email_body(
                 raw_analysis=raw_analysis, # Pass raw analysis directly
                 turkish_analysis=turkish_analysis # Pass Turkish analysis
            )
            subject = f"{config.EMAIL_SUBJECT_PREFIX} - {datetime.now().strftime('%Y-%m-%d')}"

            try:
                send_email(subject, email_body, recipients, attachment_paths)
                logger.info("Email report sent successfully.")
                success = True # Mark cycle as successful ONLY if email is sent
            except Exception as email_err:
                logger.critical(f"Failed to send email report: {email_err}", exc_info=True)
                success = False # Ensure cycle is marked as failed if email fails

    except Exception as cycle_err:
        logger.critical(f"An unexpected error occurred during the report cycle: {cycle_err}", exc_info=True)
        # Send error notification if possible
        try:
             error_subject = f"ERROR: YouTrack Report Generation Failed - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
             error_body = f"The automated report generation failed.\n\nError:\n{traceback.format_exc()}"
             recipients = config.REPORT_RECIPIENTS # Try to load recipients for error mail
             if recipients:
                 send_email(error_subject, error_body, recipients, []) # Send without attachments
                 logger.info("Sent error notification email.")
             else:
                  logger.error("Could not send error notification email - no recipients found in config.py.")
        except Exception as notify_err:
            logger.error(f"Failed to send error notification email: {notify_err}", exc_info=True)
        success = False # Ensure cycle is marked as failed

    finally:
        cycle_duration = time.time() - cycle_start_time
        logger.info(f"--- Single Report Cycle Finished --- Duration: {cycle_duration:.2f} seconds --- Success: {success} ---")
        # Clean up plot files? Maybe keep latest run?
        # For now, execute_plot_code clears previous plots each time.

    return success

def main():
    logger.info("--- Initializing YouTrack Daily Reporting Service --- ")

    # # --- Get Config from Environment --- # REMOVED these lines
    # base_url = os.getenv("YOUTRACK_BASE_URL")
    # token = os.getenv("YOUTRACK_TOKEN")
    # project_id = os.getenv("YOUTRACK_PROJECT_ID")

    # # Validate essential config first # REMOVED this block
    # if not all([base_url, token, project_id]):
    #     logger.critical("Essential YouTrack configuration (YOUTRACK_BASE_URL, YOUTRACK_TOKEN, YOUTRACK_PROJECT_ID) missing in .env. Exiting.")
    #     sys.exit(1)

    # Initialize YouTrack API client - It reads config internally
    try:
        youtrack_api = YouTrackAPI()
        # Optional: Add a log here if YouTrackAPI internal init logs success
        # logger.info(f"YouTrack API Initialized for Project: {youtrack_api.project_id}") # Access project_id after init
        logger.info(f"YouTrack API Initialized successfully.") # More generic message
    except Exception as e:
        logger.critical(f"Failed to initialize YouTrackAPI. Check config/env variables ({e}). Exiting.", exc_info=True)
        sys.exit(1)

    while True:
        logger.info(f"Starting new report cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            run_single_report_cycle(youtrack_api)
        except Exception as e:
            logger.error(f"Unhandled exception in main report loop: {e}", exc_info=True)
            # Avoid immediate retry in case of persistent unhandled errors
            logger.info("Pausing for 60 seconds due to unhandled exception before next cycle.")
            time.sleep(60)

        logger.info(f"Next report cycle scheduled in {REPORT_INTERVAL_SECONDS / 3600:.1f} hours.")
        time.sleep(REPORT_INTERVAL_SECONDS)

if __name__ == "__main__":
    # Ensure data directory exists
    if not os.path.exists('data'):
        os.makedirs('data')
        logger.info("Created data directory.")

    main() 