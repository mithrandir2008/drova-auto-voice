import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Gemini Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in .env file or environment variables.")
GEMINI_MODEL = 'gemini-1.5-flash' # Updated model name
print(f"Using Gemini model: {GEMINI_MODEL}")


# --- TTS Provider Selection ---
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs").lower()
if TTS_PROVIDER not in ["elevenlabs", "google"]:
    raise ValueError(f"Invalid TTS_PROVIDER '{TTS_PROVIDER}'. Choose 'elevenlabs' or 'google'.")
print(f"Using TTS Provider: {TTS_PROVIDER}")

# --- ElevenLabs Configuration (Required if TTS_PROVIDER='elevenlabs') ---
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_MODEL_ID = "eleven_turbo_v2" # Example model, ensure compatibility
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"

if TTS_PROVIDER == "elevenlabs" and not ELEVENLABS_API_KEY:
     raise ValueError("ELEVENLABS_API_KEY is required when TTS_PROVIDER is 'elevenlabs'.")

# --- Google TTS Configuration (Required if TTS_PROVIDER='google') ---
# GOOGLE_APPLICATION_CREDENTIALS environment variable should be set
# or the path specified in .env
GOOGLE_TTS_LANGUAGE_CODE = "en-US" # Default language
GOOGLE_TTS_AUDIO_ENCODING = "MP3" # MP3 or LINEAR16

# --- File Paths ---
DATA_DIR = os.path.dirname(os.path.abspath(__file__)) # Assumes data files are in the same dir
VOICES_PATH = os.path.join(DATA_DIR, "voices.json")
MAPPING_PATH = os.path.join(DATA_DIR, "character_voices.json")

# --- Fallback Voice ---
DEFAULT_FALLBACK_VOICE_ID = os.getenv("DEFAULT_FALLBACK_VOICE_ID")
if not DEFAULT_FALLBACK_VOICE_ID:
    # Provide sensible defaults if not set in .env
    if TTS_PROVIDER == 'elevenlabs':
        DEFAULT_FALLBACK_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb" # Rachel (example)
        print("Warning: DEFAULT_FALLBACK_VOICE_ID not set in .env, using ElevenLabs default.")
    elif TTS_PROVIDER == 'google':
        DEFAULT_FALLBACK_VOICE_ID = "en-US-Standard-A" # Google Standard Female (example)
        print("Warning: DEFAULT_FALLBACK_VOICE_ID not set in .env, using Google TTS default.")
    else:
         # Should not happen due to earlier check, but belt-and-suspenders
        DEFAULT_FALLBACK_VOICE_ID = "" # No valid fallback
        print("Warning: Could not determine a default fallback voice ID.")
else:
    print(f"Using fallback voice ID: {DEFAULT_FALLBACK_VOICE_ID}")


# --- Image Processing ---
MAX_IMAGE_HEIGHT = 720

# --- Gemini Prompt ---
SYSTEM_PROMPT = """
Analyze the character prominently featured in the screenshot provided.
Identify the character's name, gender (Male/Female/Unknown), and any dialogue they are speaking
(look for speech bubbles or text directly attributed to them). Use "Unknown" if the name or gender cannot be determined.

Return ONLY a valid JSON object with the following structure:
{
  "character_name": "<Character's Name or Unknown>",
  "gender": "<Male/Female/Unknown>",
  "dialogue": "<The character's exact spoken words as seen in the image, or an empty string if none>"
}

Do not include any explanatory text before or after the JSON object.
Ensure the 'dialogue' field contains only the text spoken by the character.
If no dialogue is clearly visible or attributable to the character, return an empty string for 'dialogue'.
"""