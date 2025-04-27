import os
from elevenlabs.client import ElevenLabs
from elevenlabs import play, save
import config # Use config for API key and settings

# --- Initialize Client ---
try:
    if not config.ELEVENLABS_API_KEY:
        # This case should ideally be caught by config.py, but check again
        raise ValueError("ElevenLabs API Key not configured.")
    eleven_client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
    print("ElevenLabs client initialized successfully.")
except Exception as e:
    print(f"Error initializing ElevenLabs client: {e}")
    # Allow script to continue but synthesize will fail later
    eleven_client = None

# --- Standardized Functions ---

def synthesize(text: str, voice_id: str, output_filename: str | None = None) -> bool:
    """
    Synthesizes text using ElevenLabs and plays the audio. Optionally saves it.
    Returns True on success, False on failure.
    """
    if not eleven_client:
        print("Error: ElevenLabs client not initialized. Cannot synthesize.")
        return False
    if not text or not text.strip():
        print("No dialogue text provided to synthesize.")
        return False
    if not voice_id:
        print("Error: No ElevenLabs Voice ID provided.")
        return False

    print(f"\nSending dialogue to ElevenLabs using Voice ID {voice_id}: '{text}'")
    try:
        audio = eleven_client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=config.ELEVENLABS_MODEL_ID,
            output_format=config.ELEVENLABS_OUTPUT_FORMAT,
            # Add stability/similarity settings here if desired, e.g.
            # stability=0.5,
            # similarity_boost=0.75,
        )

        print("Audio received from ElevenLabs. Playing...")
        play(audio)
        print("Playback finished.")

        if output_filename:
            try:
                # Ensure directory exists for saving
                os.makedirs(os.path.dirname(output_filename), exist_ok=True)
                save(audio, output_filename)
                print(f"Audio also saved to: {output_filename}")
            except Exception as e:
                print(f"Error saving audio file '{output_filename}': {e}")
                # Continue even if saving fails, as playback might have succeeded
        return True

    except Exception as e:
        print(f"Error during ElevenLabs API call or audio playback: {e}")
        return False


def get_voices() -> dict:
    """
    Fetches available English voices from ElevenLabs and returns them
    in the standardized format {'male': [...], 'female': [...]}.
    Each voice entry is a dict {'id': str, 'name': str}.
    """
    if not eleven_client:
        print("Error: ElevenLabs client not initialized. Cannot fetch voices.")
        return {'male': [], 'female': []}

    print("Fetching available voices from ElevenLabs...")
    male_voices = []
    female_voices = []
    processed_voices = 0

    try:
        # Fetch all available voices (premade & potentially shared/cloned)
        all_voices_response = eleven_client.voices.get_all()

        if not all_voices_response or not hasattr(all_voices_response, 'voices'):
            print("Warning: Could not retrieve voices or response format unexpected.")
            return {'male': [], 'female': []}

        all_voices = all_voices_response.voices
        print(f"Retrieved {len(all_voices)} total voices. Filtering for usable English voices...")

        for voice in all_voices:
            processed_voices += 1
            name = getattr(voice, 'name', 'Unnamed Voice')
            voice_id = getattr(voice, 'voice_id', None)
            category = getattr(voice, 'category', 'unknown') # premade, cloned, generated, professional

            if not voice_id:
                # print(f"Skipping voice '{name}' - missing voice_id")
                continue

            # --- Filters ---
            # 1. Check usability (e.g., skip 'generated' unless specifically needed)
            # Adjust this filter based on which voice types you want to use
            if category == 'generated' or category == 'task_carried_out': # Often unstable or temporary
                 # print(f"Skipping voice '{name}' ({voice_id}) - category: {category}")
                 continue


            # 2. Check Gender (using labels)
            gender = "unknown"
            if voice.labels and isinstance(voice.labels, dict):
                gender = voice.labels.get("gender", "unknown").lower()
                # Optional: map other labels if needed (e.g., 'description')

            # 3. Check Language (Simple check using labels - more robust check might be needed)
            # This is basic. API doesn't always expose easy language filter for *all* voice types
            is_english = False
            if voice.labels and isinstance(voice.labels, dict):
                 accent = voice.labels.get("accent", "").lower()
                 use_case = voice.labels.get("use case", "").lower()
                 # Crude check, might include non-English voices with these accents
                 if accent in ["american", "british", "english", "australian", "irish", "uk", "us"] or 'narrat' in use_case or 'audiobook' in use_case:
                      is_english = True
                 # Add description checks if useful
                 # description = voice.labels.get("description", "").lower()
                 # if 'english' in description or 'american' in description or 'british' in description:
                 #      is_english = True


            # If language check seems insufficient, consider using only voices you know,
            # or filtering based on name patterns if consistent.


            # --- Add to lists if English ---
            if is_english:
                 voice_data = {"id": voice_id, "name": name} # Standardized format
                 if gender == "male":
                     male_voices.append(voice_data)
                 elif gender == "female":
                     female_voices.append(voice_data)
                 # else: # unknown gender - could put in a separate list or ignore
                 #    print(f"Voice '{name}' ({voice_id}) has unknown gender, skipping assignment.")

        print(f"Processed {processed_voices} voices.")
        print(f"Found {len(male_voices)} potential English male voices and {len(female_voices)} potential English female voices.")
        return {"male": male_voices, "female": female_voices}

    except Exception as e:
        print(f"Error fetching or processing ElevenLabs voices: {e}")
        return {'male': [], 'female': []}