import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Interactive Listener Settings ---
TRIGGER_KEY = "`" # Tilde key (often above Tab)
EXIT_KEY = "esc" # Escape key


# --- Gemini Configuration ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in .env file or environment variables.")
GEMINI_MODEL = 'gemini-2.0-flash' # Updated model name
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


# Load the voice name filter(s) from .env (default to empty list = no filter)
_raw_filter_str = os.getenv("GOOGLE_VOICE_FILTER", "").strip()
# Split by comma, strip whitespace from each part, convert to lower, and remove empty strings
GOOGLE_VOICE_FILTERS = [f.strip().lower() for f in _raw_filter_str.split(',') if f.strip()] # <-- PROCESS INTO A LIST

if GOOGLE_VOICE_FILTERS:                                                # <-- CHECK IF LIST IS NOT EMPTY
    print(f"Applying Google TTS voice name filters: {GOOGLE_VOICE_FILTERS}") # <-- SHOW THE LIST
else:
    print("No Google TTS voice name filter applied.")



# --- File Paths ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__)) # Get the directory where config.py lives
DATA_DIR = os.path.join(PROJECT_ROOT, "data") # Define the data subfolder path <--- CHANGE HERE
VOICES_PATH = os.path.join(DATA_DIR, "voices.json") # Will now point inside 'data/'
MAPPING_PATH = os.path.join(DATA_DIR, "character_voices.json") # Will now point inside 'data/'

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

# # --- Gemini Prompt ---
# SYSTEM_PROMPT = """
# Analyze the character prominently featured in the screenshot provided.
# Identify the character's name, gender (Male/Female/Unknown), and any dialogue they are speaking
# (look for speech bubbles or text directly attributed to them). Use "Unknown" if the name or gender cannot be determined.

# Return ONLY a valid JSON object with the following structure:
# {
#   "character_name": "<Character's Name or Unknown>",
#   "gender": "<Male/Female/Unknown>",
#   "dialogue": "<The character's exact spoken words as seen in the image, or an empty string if none>"
# }

# Do not include any explanatory text before or after the JSON object.
# Ensure the 'dialogue' field contains only the text spoken by the character.
# If no dialogue is clearly visible or attributable to the character, return an empty string for 'dialogue'.
# """

# --- Gemini Prompt with Google Chirp3-HD Pauses---
SYSTEM_PROMPT = """
Analyze the character prominently featured in the screenshot provided.
Identify the character's name and gender (Male/Female/Unknown).
Extract the dialogue they are speaking (look for speech bubbles or text directly attributed to them).

**Rewrite the extracted dialogue to sound more natural for text-to-speech, focusing on pacing and flow.**
Use punctuation strategically:
- Periods (.) for sentence endings and clear pauses.
- Commas (,) for shorter pauses within sentences (e.g., separating clauses, list items).
- Ellipses (...) for hesitations, trailing thoughts, or more significant pauses.
- Hyphens (-) *occasionally* for abrupt breaks or slight pauses, if appropriate.
- Aim for conversational phrasing where fitting. Break down long sentences if needed.
- Do NOT just return the raw text. Enhance it with punctuation for better TTS delivery.
- If no dialogue is visible, return an empty string for 'dialogue'.

Return ONLY a valid JSON object with the following structure:
{
  "character_name": "<Character's Name or Unknown>",
  "gender": "<Male/Female/Unknown>",
  "dialogue": "<The REWRITTEN dialogue using punctuation for natural flow>"
}

Do not include any explanatory text before or after the JSON object.
Ensure the 'dialogue' field contains the rewritten plain text or an empty string.
"""

# --- Gemini Prompt with SSML ---
# SYSTEM_PROMPT = """
# Analyze the character prominently featured in the screenshot provided.
# Identify the character's name, gender (Male/Female/Unknown).
# Analyze the dialogue they are speaking (look for speech bubbles or text directly attributed to them).

# Format the dialogue using basic SSML (Speech Synthesis Markup Language) to improve naturalness for text-to-speech.
# Specifically:
# 1. Wrap the entire dialogue content within `<speak>` tags.
# 2. Use `<break strength="medium"/>` where a comma or short natural pause would occur within a sentence.
# 3. Use `<break strength="strong"/>` or `<break time="0.7s"/>` at the end of sentences or where a more significant pause is appropriate.
# 4. Optionally, use `<emphasis level="moderate">word</emphasis>` for words that seem emphasized in the context.
# 5. Do NOT overuse SSML tags. Aim for subtle improvements in flow.
# 6. If no dialogue is visible, return an empty string for 'dialogue_ssml'.

# Return ONLY a valid JSON object with the following structure:
# {
#   "character_name": "<Character's Name or Unknown>",
#   "gender": "<Male/Female/Unknown>",
#   "dialogue_ssml": "<speak>The character's dialogue with SSML tags, e.g., <break strength='medium'/> Let's go.</speak>"
# }

# Do not include any explanatory text before or after the JSON object. Ensure the 'dialogue_ssml' field contains valid XML/SSML within the `<speak>` tags or an empty string.
# """