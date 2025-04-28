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
    Dynamically determines language code from the voice_id.
    Returns True on success, False on failure.
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

    # --- Dynamically determine language code from voice_id ---
    extracted_language_code = config.GOOGLE_TTS_LANGUAGE_CODE # Default fallback
    try:
        parts = voice_id.split('-')
        if len(parts) >= 2:
            # Assume format like 'en-US-Wavenet-A' or 'en-AU-Chirp...'
            # Combine the first two parts for the language code (e.g., 'en-US', 'en-AU')
            # Google uses BCP-47 tags, so 'en-US' or 'en-AU' is correct.
            parsed_code = f"{parts[0]}-{parts[1]}"
            # Basic validation (e.g., check if it looks like xx-XX) - Can be improved
            # This check is simplified, assumes 2-letter lang and 2-letter region primarily
            if len(parsed_code) == 5 and parsed_code[2] == '-' and parsed_code[:2].isalpha() and parsed_code[3:].isalpha():
                 extracted_language_code = parsed_code
                 # print(f"Extracted language code '{extracted_language_code}' from voice ID.") # Optional debug print
            else:
                 print(f"Warning: Could not reliably parse standard language code format (xx-XX) from start of voice ID '{voice_id}'. Using default '{extracted_language_code}'.")
        else:
            print(f"Warning: Voice ID '{voice_id}' format unexpected (less than 2 parts after split by '-'). Using default '{extracted_language_code}'.")
    except Exception as e:
        print(f"Warning: Error parsing language code from voice ID '{voice_id}': {e}. Using default '{extracted_language_code}'.")
    # --- End of language code extraction ---


    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Use voice_id directly as the name parameter
        # Use the *extracted* language code
        voice = texttospeech.VoiceSelectionParams(
            language_code=extracted_language_code, # <--- USE EXTRACTED CODE HERE
            name=voice_id
        )

        # Select the type of audio file format (MP3 or WAV/LINEAR16)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=getattr(texttospeech.AudioEncoding, config.GOOGLE_TTS_AUDIO_ENCODING)
            # You could add pitch, speaking_rate here if desired
            # speaking_rate=1.0,
            # pitch=0.0
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
            # Only print if playback was expected but libs missing
            # This check is now done at the top, so just note skipping.
            # print("Audio playback skipped (libraries not available).")
            pass


        # Save to file
        saved_successfully = False
        if output_filename:
            try:
                # Ensure directory exists
                output_dir = os.path.dirname(output_filename)
                if output_dir: # Check if there is a directory part
                     os.makedirs(output_dir, exist_ok=True)

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
        # This will now catch the 400 error if parsing failed AND default was also wrong,
        # or any other API/audio handling errors.
        print(f"Error during Google TTS API call or audio handling: {e}")
        return False

def get_voices() -> dict:
    """
    Fetches available English voices from Google TTS, optionally filtering
    by name substrings specified in config.GOOGLE_VOICE_FILTERS (list), and
    returns them in the standardized format {'male': [...], 'female': [...]}.
    Each voice entry is a dict {'id': str, 'name': str}.
    'id' for Google TTS is the voice name (e.g., 'en-US-Wavenet-D').
    """
    if not google_client:
        print("Error: Google TTS client not initialized. Cannot fetch voices.")
        return {'male': [], 'female': []}

    print("Fetching available voices from Google Cloud TTS...")
    # --->>> INITIALIZE THE LISTS HERE <<<---
    male_voices = []
    female_voices = []

    try:
        response = google_client.list_voices() # Gets all voices

        # Check if the filter list in config is not empty
        filters_active = bool(config.GOOGLE_VOICE_FILTERS)

        print(f"Retrieved {len(response.voices)} total voices. Filtering for English"
              f"{' and names containing any of: ' + str(config.GOOGLE_VOICE_FILTERS) if filters_active else ''}...")

        # --->>> REMOVE INITIALIZATION FROM INSIDE TRY (if it was accidentally left here) <<<---
        # male_voices = [] # Remove if present here
        # female_voices = [] # Remove if present here

        for voice in response.voices:
            # Filter 1: Language (must contain an 'en' code)
            is_english = any(lc.startswith('en') for lc in voice.language_codes)
            if not is_english:
                continue # Skip non-English voices

            # Filter 2: Voice Name Substring (if filters are active)
            if filters_active:
                voice_name_lower = voice.name.lower()
                # Check if the voice name contains *any* of the filter strings
                matches_any_filter = any(f_keyword in voice_name_lower for f_keyword in config.GOOGLE_VOICE_FILTERS)
                if not matches_any_filter:
                    continue # Skip voice if its name doesn't contain ANY of the required filter strings

            # --- If the voice passed all filters, process it ---
            # Map Google's gender enum to our simple strings
            gender = "unknown"
            if voice.ssml_gender == texttospeech.SsmlVoiceGender.MALE:
                gender = "male"
            elif voice.ssml_gender == texttospeech.SsmlVoiceGender.FEMALE:
                gender = "female"

            # Standardized format
            voice_data = {"id": voice.name, "name": voice.name}

            if gender == "male":
                male_voices.append(voice_data)
            elif gender == "female":
                female_voices.append(voice_data)

        print(f"Found {len(male_voices)} English male voices and {len(female_voices)} English female voices matching the criteria.")
        # This return is fine as lists are guaranteed to exist if success
        return {"male": male_voices, "female": female_voices}

    except Exception as e:
        print(f"Error fetching or processing Google TTS voices: {e}")
        # This return is now safe because male_voices/female_voices were initialized before the try block
        # It correctly returns empty lists on error.
        return {'male': [], 'female': []}