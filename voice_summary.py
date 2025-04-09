import os
from elevenlabs.client import ElevenLabs
from elevenlabs import save
from dotenv import load_dotenv
import logging
import tempfile
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# --- Configuration ---
# You might want to make the voice configurable via .env or settings page later
DEFAULT_VOICE = "Rachel"
DEFAULT_MODEL = "eleven_multilingual_v2"
AUDIO_OUTPUT_DIR = "generated_audio" # Directory to save audio files
# ---

def initialize_client():
    """Initializes and returns the ElevenLabs client."""
    if not ELEVENLABS_API_KEY:
        logging.error("ELEVENLABS_API_KEY not found in environment variables.")
        return None
    try:
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        logging.info("ElevenLabs client initialized successfully.")
        return client
    except Exception as e:
        logging.error(f"Failed to initialize ElevenLabs client: {e}")
        return None

def generate_audio_summary(text_summary, voice=DEFAULT_VOICE, model=DEFAULT_MODEL):
    """
    Generates an audio summary using the ElevenLabs API and saves it to a temporary file.

    Args:
        text_summary (str): The text content to convert to speech.
        voice (str): The name of the voice to use.
        model (str): The model to use for generation.

    Returns:
        str: The path to the generated audio file (MP3), or None if generation failed.
    """
    client = initialize_client()
    if not client:
        return None

    if not text_summary:
        logging.warning("No text summary provided for audio generation.")
        return None

    try:
        logging.info(f"Generating audio summary with voice '{voice}' and model '{model}'.")
        audio = client.generate(
            text=text_summary,
            voice=voice,
            model=model
        )

        # Create a unique filename in a temporary directory
        # Using a temporary directory is often safer than writing directly to project dirs
        # Alternatively, save to AUDIO_OUTPUT_DIR if persistent storage is needed
        # os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
        # filename = f"daily_summary_{uuid.uuid4()}.mp3"
        # output_path = os.path.join(AUDIO_OUTPUT_DIR, filename)

        # Using tempfile for automatic cleanup unless file is needed long-term
        temp_dir = tempfile.gettempdir()
        filename = f"youtrack_summary_{uuid.uuid4()}.mp3"
        output_path = os.path.join(temp_dir, filename)


        save(audio, output_path)
        logging.info(f"Audio summary saved successfully to: {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Error during ElevenLabs audio generation or saving: {e}")
        return None

if __name__ == '__main__':
    # Example usage (for testing purposes)
    logging.info("Testing voice_summary module...")
    test_text = "This is a test summary. Issue YT-123 is blocked. Team Alpha velocity increased by 10%."
    # To test generation, ensure .env has ELEVENLABS_API_KEY and uncomment below:
    # audio_file_path = generate_audio_summary(test_text)
    # if audio_file_path:
    #     logging.info(f"Test audio file generated at: {audio_file_path}")
    #     # Consider adding cleanup here if using tempfile isn't desired long-term
    #     # os.remove(audio_file_path)
    # else:
    #     logging.error("Test audio generation failed.")
    logging.info("Voice summary module test structure seems okay.")
