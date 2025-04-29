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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash") # Use 1.5 Flash as default if not set
print(f"Using Gemini model: {GEMINI_MODEL}")


# --- TTS Provider Selection ---
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs").lower()
VALID_TTS_PROVIDERS = ["elevenlabs", "google", "openai"] # Add openai to valid list
if TTS_PROVIDER not in VALID_TTS_PROVIDERS:
    raise ValueError(f"Invalid TTS_PROVIDER '{TTS_PROVIDER}'. Choose from: {', '.join(VALID_TTS_PROVIDERS)}.")
print(f"Using TTS Provider: {TTS_PROVIDER}")

# --- ElevenLabs Configuration (Required if TTS_PROVIDER='elevenlabs') ---
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2") # Default model
ELEVENLABS_OUTPUT_FORMAT = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128") # Default format

if TTS_PROVIDER == "elevenlabs" and not ELEVENLABS_API_KEY:
     raise ValueError("ELEVENLABS_API_KEY is required when TTS_PROVIDER is 'elevenlabs'.")
elif TTS_PROVIDER == "elevenlabs":
    print(f"  ElevenLabs Model: {ELEVENLABS_MODEL_ID}")
    print(f"  ElevenLabs Output Format: {ELEVENLABS_OUTPUT_FORMAT}")

# --- Google TTS Configuration (Required if TTS_PROVIDER='google') ---
# GOOGLE_APPLICATION_CREDENTIALS environment variable should be set
# or the path specified in .env
GOOGLE_TTS_LANGUAGE_CODE = os.getenv("GOOGLE_TTS_LANGUAGE_CODE", "en-US") # Default language
GOOGLE_TTS_AUDIO_ENCODING = os.getenv("GOOGLE_TTS_AUDIO_ENCODING", "MP3").upper() # MP3 or LINEAR16

if TTS_PROVIDER == "google" and GOOGLE_TTS_AUDIO_ENCODING not in ["MP3", "LINEAR16"]:
    print(f"Warning: Invalid GOOGLE_TTS_AUDIO_ENCODING '{GOOGLE_TTS_AUDIO_ENCODING}'. Using 'MP3'.")
    GOOGLE_TTS_AUDIO_ENCODING = "MP3"

# Load the voice name filter(s) from .env (default to empty list = no filter)
_raw_filter_str = os.getenv("GOOGLE_VOICE_FILTER", "").strip()
# Split by comma, strip whitespace from each part, convert to lower, and remove empty strings
GOOGLE_VOICE_FILTERS = [f.strip().lower() for f in _raw_filter_str.split(',') if f.strip()]

if TTS_PROVIDER == "google":
    print(f"  Google Language Code: {GOOGLE_TTS_LANGUAGE_CODE}")
    print(f"  Google Audio Encoding: {GOOGLE_TTS_AUDIO_ENCODING}")
    if GOOGLE_VOICE_FILTERS:
        print(f"  Applying Google TTS voice name filters: {GOOGLE_VOICE_FILTERS}")
    else:
        print("  No Google TTS voice name filter applied.")

# --- OpenAI TTS Configuration (Required if TTS_PROVIDER='openai') ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1") # Default model (e.g., tts-1, tts-1-hd)
# Note: OpenAI output format is requested in the API call (wav for playback, mp3 default)
# This config value could be used as a fallback if needed, but the tts_openai.py script handles it.
OPENAI_TTS_DEFAULT_FORMAT = os.getenv("OPENAI_TTS_DEFAULT_FORMAT", "mp3").lower() # Default format if saved without playback libs

if TTS_PROVIDER == "openai" and not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is required when TTS_PROVIDER is 'openai'.")
elif TTS_PROVIDER == "openai":
    print(f"  OpenAI Model: {OPENAI_TTS_MODEL}")
    print(f"  OpenAI Default Save Format: {OPENAI_TTS_DEFAULT_FORMAT}")
    # Add validation for format if desired (mp3, opus, aac, flac, wav, pcm)


# --- File Paths ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__)) # Get the directory where config.py lives
DATA_DIR = os.path.join(PROJECT_ROOT, "data") # Define the data subfolder path
os.makedirs(DATA_DIR, exist_ok=True) # Ensure data directory exists
VOICES_PATH = os.path.join(DATA_DIR, "voices.json") # Will now point inside 'data/'
MAPPING_PATH = os.path.join(DATA_DIR, "character_voices.json") # Will now point inside 'data/'

# --- Fallback Voice ---
DEFAULT_FALLBACK_VOICE_ID = os.getenv("DEFAULT_FALLBACK_VOICE_ID")
if not DEFAULT_FALLBACK_VOICE_ID:
    # Provide sensible defaults if not set in .env, specific to the selected provider
    if TTS_PROVIDER == 'elevenlabs':
        DEFAULT_FALLBACK_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb" # Rachel (example)
        print("Warning: DEFAULT_FALLBACK_VOICE_ID not set in .env, using ElevenLabs default (Rachel).")
    elif TTS_PROVIDER == 'google':
        DEFAULT_FALLBACK_VOICE_ID = "en-US-Standard-A" # Google Standard Female (example)
        print("Warning: DEFAULT_FALLBACK_VOICE_ID not set in .env, using Google TTS default (en-US-Standard-A).")
    elif TTS_PROVIDER == 'openai':
        DEFAULT_FALLBACK_VOICE_ID = "nova" # OpenAI Nova (female example)
        print("Warning: DEFAULT_FALLBACK_VOICE_ID not set in .env, using OpenAI default (nova).")
    else:
         # Should not happen due to earlier check, but for completeness
        DEFAULT_FALLBACK_VOICE_ID = "" # No valid fallback
        print("Warning: Could not determine a default fallback voice ID for the selected provider.")
else:
    print(f"Using fallback voice ID: {DEFAULT_FALLBACK_VOICE_ID}")


# --- Audio Settings ---
try:
    TARGET_SAMPLE_RATE = int(os.getenv("TARGET_SAMPLE_RATE", "48000")) # Load as int, default 48k
    if TARGET_SAMPLE_RATE <= 0:
        print(f"Warning: Invalid TARGET_SAMPLE_RATE ({TARGET_SAMPLE_RATE}). Using default 48000 Hz.")
        TARGET_SAMPLE_RATE = 48000
    print(f"Target TTS Sample Rate: {TARGET_SAMPLE_RATE} Hz (Note: Actual output rate may vary by provider/settings)")
except ValueError:
    print(f"Warning: TARGET_SAMPLE_RATE in .env is not a valid integer. Using default 48000 Hz.")
    TARGET_SAMPLE_RATE = 48000

# --- Image Processing ---
MAX_IMAGE_HEIGHT = 480 # Consider making this configurable via .env if needed

# --- Gemini Prompt ---
# Choose one of the prompts below by uncommenting it.
# Make sure only ONE prompt is active.

# Option 1: Simple Punctuation Enhancement (Default)
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

# Option 2: Basic SSML Enhancement (Use if TTS provider supports SSML well, e.g., Google)
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

print(f"System prompt type configured: {'Simple Punctuation' if 'REWRITTEN dialogue' in SYSTEM_PROMPT else 'SSML Enhancement'}")