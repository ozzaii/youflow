import smtplib
import ssl
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from dotenv import load_dotenv
import re
from datetime import datetime
from typing import List, Optional
from config import EMAIL_ENABLED, REPORT_RECIPIENTS # Import from config
import markdown

# Configure logging specific to this module
# Get a logger instance specific to this file
logger = logging.getLogger(__name__)
# Set the level *for this specific logger* to DEBUG
# This is more reliable than relying only on basicConfig if other modules configure logging
logger.setLevel(logging.DEBUG) 

# Keep basicConfig for root logger/other modules if needed, but ensure it doesn't suppress our logger
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s') 
# logger = logging.getLogger(__name__) # Already defined above

# Load environment variables from .env file
load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
RECIPIENTS_FILE = "recipients.txt"

def _load_recipients() -> List[str]:
    """Loads recipients from environment or config."""
    recipients_str = os.getenv('REPORT_RECIPIENTS')
    if recipients_str:
        return [email.strip() for email in recipients_str.split(',')]
    elif REPORT_RECIPIENTS: # Use config list if env var not set
        return REPORT_RECIPIENTS
    else:
        logging.warning("No email recipients found in environment variables (REPORT_RECIPIENTS) or config.py (REPORT_RECIPIENTS).")
        return []

def _prepare_email_message(subject: str, body_html: str, sender: str, recipients: List[str], attachments: List[str] = None) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)

    # Attach the HTML body
    message.attach(MIMEText(body_html, "html"))

    # Attach files if provided
    if attachments:
        for path in attachments:
            if not path or not os.path.exists(path):
                logging.warning(f"Attachment file not found or invalid path: {path}. Skipping.")
                continue # Skip this file
            try:
                with open(path, "rb") as attachment:
                    part = MIMEApplication(attachment.read(), Name=os.path.basename(path))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(path)}"'
                message.attach(part)
                logging.info(f"Attached file: {path}")
            except Exception as e:
                logging.error(f"Error attaching file {path}: {e}")
                # Continue sending email without this specific attachment if attaching fails

    return message

def send_email(subject: str, body_html: str, recipients: List[str], attachments: List[str] = None):
    """Sends an email using SMTP_SSL, attaching multiple files if provided."""
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SENDER_EMAIL]):
        logging.error("SMTP configuration is incomplete. Please check your .env file.")
        return False
    if not recipients:
        logging.error("No recipients provided or loaded.")
        return False

    port = int(SMTP_PORT)
    # Create an SSL context that does NOT verify certificates (less secure, for testing)
    context = ssl._create_unverified_context()
    # context = ssl.create_default_context()

    try:
        # Use SMTP_SSL for direct SSL connection
        with smtplib.SMTP_SSL(SMTP_HOST, port, context=context) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            logging.info(f"Logged in to SMTP server: {SMTP_HOST} using SSL")

            # Prepare message ONCE with all recipients for the header
            message = _prepare_email_message(subject, body_html, SENDER_EMAIL, recipients, attachments)

            # Send to each recipient individually (for envelope)
            sent_count = 0
            failed_recipients = []
            for recipient in recipients:
                try:
                    # Use the single recipient for the sendmail envelope address
                    server.sendmail(SENDER_EMAIL, recipient, message.as_string())
                    logging.info(f"Email sent successfully to {recipient}")
                    sent_count += 1
                except Exception as e:
                    logging.error(f"Failed to send email to {recipient}: {e}")
                    failed_recipients.append(recipient)
            
            if failed_recipients:
                 logging.warning(f"Email sending finished. Success: {sent_count}/{len(recipients)}. Failed for: {', '.join(failed_recipients)}")
                 return False # Indicate partial or full failure
            else:
                logging.info(f"Email sending finished. Success: {sent_count}/{len(recipients)}.")
                return True # Indicate all successful

    except smtplib.SMTPConnectError:
        logging.error(f"Failed to connect to SMTP server {SMTP_HOST}:{port}.")
        return False
    except smtplib.SMTPException as e: # Catch broader SMTP exceptions
        logging.error(f"SMTP Error: {e}")
    except ssl.SSLError as e: # Catch SSL errors specifically again
        logging.error(f"SSL Error connecting to SMTP server: {e}. Check port/method or local certificate store.")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred during email sending: {e}")
        return False

def create_leadership_email_body(raw_analysis: str, turkish_analysis: Optional[str] = None) -> str:
    """Creates the HTML body for the leadership email report, optionally including Turkish translation."""
    # Get current timestamp for the report
    current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Basic HTML structure with inline CSS for compatibility
    html_start = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MQ EIS/KG BSW - Daily Intelligence Report</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f4; }}
            .container {{ max-width: 800px; margin: 20px auto; background-color: #ffffff; padding: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            h1 {{ color: #003366; font-size: 24px; border-bottom: 2px solid #003366; padding-bottom: 10px; margin-top: 0; }}
            h2 {{ color: #0055A4; font-size: 20px; margin-top: 25px; border-bottom: 1px solid #e0e0e0; padding-bottom: 5px; }}
            h3 {{ color: #333; font-size: 16px; margin-top: 20px; }}
            p, ul, li {{ font-size: 14px; margin-bottom: 10px; }}
            ul {{ padding-left: 20px; list-style-type: disc; }} /* Ensure list style */
            li {{ margin-bottom: 5px; }}
            strong {{ font-weight: bold; }} /* Standard bold */
            .section {{ margin-bottom: 20px; padding: 15px; background-color: #f9f9f9; border-left: 4px solid #0055A4; border-radius: 4px; }}
            .report-content {{ margin-top: 15px; }}
            .divider {{ border-top: 1px dashed #ccc; margin: 30px 0; }}
            .footer {{ margin-top: 30px; text-align: center; font-size: 12px; color: #777; }}
            /* Ensure AI-generated markdown bold doesn't override */
            b, strong {{ font-weight: bold !important; color: inherit !important; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>MQ EIS/KG BSW - Daily Intelligence Report</h1>
            <p><strong>Generated:</strong> {current_timestamp}</p>

            <div class="report-content">
                <h2>AI Analysis (English)</h2>
                <div>
    """
    
    # Use MARKDOWN LIBRARY FOR CONVERSION
    # Use the module-specific logger instance
    logger.debug(f"--- Raw English Analysis ---:\n{raw_analysis}\n--- END RAW ENGLISH ---")
    try:
        html_analysis = markdown.markdown(raw_analysis, extensions=['fenced_code', 'tables'])
        logger.debug(f"--- Processed English HTML ---:\n{html_analysis}\n--- END ENGLISH HTML ---")
    except Exception as md_err:
        logger.error(f"Error processing English markdown: {md_err}")
        html_analysis = f"<p>Error processing English analysis: {md_err}</p><pre>{raw_analysis}</pre>" # Fallback
    
    # Start building the middle part
    html_middle = f"                {html_analysis}\n                </div>"
    
    # --- ADD TURKISH SECTION --- 
    if turkish_analysis:
        # Use the module-specific logger instance
        logger.debug(f"--- Raw Turkish Analysis ---:\n{turkish_analysis}\n--- END RAW TURKISH ---")
        try:
            html_turkish = markdown.markdown(turkish_analysis, extensions=['fenced_code', 'tables'])
            logger.debug(f"--- Processed Turkish HTML ---:\n{html_turkish}\n--- END TURKISH HTML ---")
        except Exception as md_err:
            logger.error(f"Error processing Turkish markdown: {md_err}")
            html_turkish = f"<p>Error processing Turkish analysis: {md_err}</p><pre>{turkish_analysis}</pre>" # Fallback
        
        # SIMPLIFIED CONCATENATION
        html_middle += """
                <div class="divider"></div>
                <h2>AI Analizi (Türkçe)</h2>
                <div>
        """
        html_middle += html_turkish # Append the processed HTML
        html_middle += "                </div>" # Close the div
    # --- END TURKISH SECTION --- 

    html_end = """
            </div>
            <div class="footer">
                This report was automatically generated.
            </div>
        </div>
    </body>
    </html>
    """
    return html_start + html_middle + html_end

# --- Example Usage (for testing) ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Testing email reporter...")
    # Load recipients from file
    test_recipients = _load_recipients()
    if test_recipients:
        # Corrected example call: returns only body
        test_html_body = create_leadership_email_body("This is **test** analysis.\n\n- Item 1\n- Item 2\n\n### Subheading", "Bu test analizi (Türkçe).\n\n- Öğe 1\n- Öğe 2\n\n### Alt Başlık")
        test_subject = f"Test Email - {datetime.now().strftime('%Y-%m-%d')}" # Set subject here for test
        success = send_email(test_subject, test_html_body, test_recipients)
        if success:
            logger.info(f"Test email sent successfully to: {test_recipients}")
        else:
            logger.error("Test email sending failed.")
    else:
        logger.warning("No recipients found in recipients.txt for testing.")
