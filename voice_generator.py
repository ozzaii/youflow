# voice_generator.py
import os
import logging
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs import save
from elevenlabs import Voice, VoiceSettings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Initialize ElevenLabs client
client = None
if ELEVENLABS_API_KEY:
    try:
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        logging.info("ElevenLabs client initialized successfully.")
        # Optional: Check available voices
        # voices = client.voices.get_all()
        # logging.info(f"Available voices: {[v.name for v in voices.voices]}")
    except Exception as e:
        logging.error(f"Failed to initialize ElevenLabs client: {e}")
        client = None
else:
    logging.warning("ElevenLabs API key not found in .env file. Voice generation disabled.")

# Define a default voice ID (You can change this - find IDs via ElevenLabs website or API)
# Example: "Rachel" voice ID
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

def generate_voice_summary(text_content: str, output_filename: str, voice_id: str = DEFAULT_VOICE_ID) -> str:
    """Generates an MP3 voice summary using the ElevenLabs API.

    Args:
        text_content: The text to synthesize.
        output_filename: The path to save the generated MP3 file.
        voice_id: The ID of the ElevenLabs voice to use.

    Returns:
        The path to the generated MP3 file if successful, None if any exception occurs.
    """
    if not client:
        logging.error("ElevenLabs client not initialized. Cannot generate voice summary.")
        return None
    if not text_content:
        logging.warning("No text content provided for voice summary.")
        return None

    try:
        logging.info(f"Generating voice summary using voice ID {voice_id}...")
        # Generate audio using the client
        audio_stream = client.generate(
            text=text_content,
            voice=voice_id,
            model="eleven_multilingual_v2" # Or another suitable model
        )

        # Ensure output directory exists (if filename includes a path)
        output_dir = os.path.dirname(output_filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logging.info(f"Created output directory: {output_dir}")

        # Save the audio stream to the specified file
        with open(output_filename, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)
        
        logging.info(f"Voice summary saved successfully to {output_filename}")
        return output_filename # RETURN FILENAME ON SUCCESS

    except Exception as e: # Catch general Exception
        # Check if it looks like an API error if needed (optional)
        # if hasattr(e, 'status_code') and hasattr(e, 'message'):
        #     logger.error(f"ElevenLabs API Error: {e.status_code} - {e.message}")
        # else:
        logging.error(f"An unexpected error occurred during voice generation: {e}", exc_info=True)
        return None # Return None on error

# --- Example Usage (for testing) ---
if __name__ == "__main__":
    logging.info("Testing voice_generator.py...")
    if not client:
        logging.error("Cannot run test: ElevenLabs client not initialized (check API key).")
    else:
        test_text = "This is a test of the ElevenLabs voice generation system for the YouTrack analytics platform."
        test_output_file = "data/test_voice_summary.mp3" # Save in data directory
        logging.info(f"Attempting to generate test audio file: {test_output_file}")
        result = generate_voice_summary(test_text, test_output_file)
        if result:
            logging.info("Test voice generation successful.")
        else:
            logging.error("Test voice generation failed.") 