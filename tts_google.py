import os
from google.cloud import texttospeech
import config # Use config for settings
import io

# Optional: For audio playback directly (requires sounddevice, soundfile)
try:
    import sounddevice as sd
    import soundfile as sf
    SOUND_LIBS_AVAILABLE = True
except ImportError:
    print("Warning: 'sounddevice' or 'soundfile' not installed. Google TTS playback disabled.")
    SOUND_LIBS_AVAILABLE = False

# --- Initialize Client ---
# Authentication is handled implicitly if GOOGLE_APPLICATION_CREDENTIALS is set
try:
    google_client = texttospeech.TextToSpeechClient()
    print("Google Cloud Text-to-Speech client initialized successfully.")
except Exception as e:
    print(f"Error initializing Google Cloud Text-to-Speech client: {e}")
    print("Ensure 'GOOGLE_APPLICATION_CREDENTIALS' environment variable is set correctly.")
    google_client = None

# --- Standardized Functions ---

def synthesize(text: str, voice_id: str, output_filename: str | None = None) -> bool:
    """
    Synthesizes text using Google TTS and plays or saves the audio.
    Returns True on success, False on failure.
    Note: `voice_id` for Google is the voice *name* (e.g., 'en-US-Wavenet-D').
    """
    if not google_client:
        print("Error: Google TTS client not initialized. Cannot synthesize.")
        return False
    if not text or not text.strip():
        print("No dialogue text provided to synthesize.")
        return False
    if not voice_id:
        print("Error: No Google TTS Voice Name (ID) provided.")
        return False

    print(f"\nSending dialogue to Google TTS using Voice Name {voice_id}: '{text}'")

    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Use voice_id directly as the name parameter
        voice = texttospeech.VoiceSelectionParams(
            language_code=config.GOOGLE_TTS_LANGUAGE_CODE, # Use language from config
            name=voice_id # Google uses the 'name' field as the identifier
        )

        # Select the type of audio file format (MP3 or WAV/LINEAR16)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=getattr(texttospeech.AudioEncoding, config.GOOGLE_TTS_AUDIO_ENCODING)
        )

        response = google_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        # --- Handle Audio Output ---
        audio_content = response.audio_content
        print("Audio received from Google TTS.")

        # Playback (Optional, requires sounddevice/soundfile)
        played_successfully = False
        if SOUND_LIBS_AVAILABLE:
            try:
                # Use soundfile to read the audio data from memory
                # Need to wrap the bytes in a BytesIO object
                audio_data, samplerate = sf.read(io.BytesIO(audio_content))
                print(f"Playing audio ({samplerate} Hz)...")
                sd.play(audio_data, samplerate)
                sd.wait() # Wait for playback to finish
                print("Playback finished.")
                played_successfully = True
            except Exception as e:
                print(f"Error playing Google TTS audio: {e}")
                print("Audio data may still be saved if an output path is provided.")
        else:
            print("Audio playback skipped (libraries not available).")


        # Save to file
        saved_successfully = False
        if output_filename:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(output_filename), exist_ok=True)
                with open(output_filename, "wb") as out:
                    out.write(audio_content)
                print(f"Audio saved to: {output_filename}")
                saved_successfully = True
            except Exception as e:
                print(f"Error saving Google TTS audio file '{output_filename}': {e}")
        else:
            # If no output filename, consider saving successful if playback worked (or if playback libs absent)
             saved_successfully = played_successfully or not SOUND_LIBS_AVAILABLE


        # Return True if either playback or saving (if requested) was successful
        return saved_successfully or (played_successfully and not output_filename)


    except Exception as e:
        print(f"Error during Google TTS API call or audio handling: {e}")
        return False


def get_voices() -> dict:
    """
    Fetches available English voices from Google TTS and returns them
    in the standardized format {'male': [...], 'female': [...]}.
    Each voice entry is a dict {'id': str, 'name': str}.
    'id' for Google TTS is the voice name (e.g., 'en-US-Wavenet-D').
    """
    if not google_client:
        print("Error: Google TTS client not initialized. Cannot fetch voices.")
        return {'male': [], 'female': []}

    print("Fetching available voices from Google Cloud TTS...")
    male_voices = []
    female_voices = []

    try:
        # Request voices (can filter by language_code='en' here or filter below)
        response = google_client.list_voices() # Gets all voices

        print(f"Retrieved {len(response.voices)} total voices. Filtering for English...")

        for voice in response.voices:
            # Filter for English language codes (e.g., en-US, en-GB, en-AU, etc.)
            is_english = any(lc.startswith('en') for lc in voice.language_codes)

            if is_english:
                # Map Google's gender enum to our simple strings
                gender = "unknown"
                if voice.ssml_gender == texttospeech.SsmlVoiceGender.MALE:
                    gender = "male"
                elif voice.ssml_gender == texttospeech.SsmlVoiceGender.FEMALE:
                    gender = "female"
                # NEUTRAL voices could be added to a separate list or ignored

                # Standardized format: Use Google's 'name' as the 'id'
                voice_data = {"id": voice.name, "name": voice.name}

                if gender == "male":
                    male_voices.append(voice_data)
                elif gender == "female":
                    female_voices.append(voice_data)

        print(f"Found {len(male_voices)} English male voices and {len(female_voices)} English female voices.")
        return {"male": male_voices, "female": female_voices}

    except Exception as e:
        print(f"Error fetching or processing Google TTS voices: {e}")
        return {'male': [], 'female': []}