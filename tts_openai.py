import os
import requests
import config
import io
import time
import numpy as np
import threading
import traceback

# --- Constants ---
OPENAI_API_URL = "https://api.openai.com/v1/audio/speech"

# Optional: For audio playback directly (requires sounddevice, soundfile)
try:
    import sounddevice as sd
    import soundfile as sf
    SOUND_LIBS_AVAILABLE = True
except ImportError:
    print("Warning: 'sounddevice' or 'soundfile' not installed. OpenAI TTS playback disabled.")
    SOUND_LIBS_AVAILABLE = False

# --- Check API Key ---
OPENAI_API_KEY = getattr(config, 'OPENAI_API_KEY', None)
if not OPENAI_API_KEY:
    print("Error: OPENAI_API_KEY not found in config.py. OpenAI TTS module disabled.")
else:
    print("OpenAI API Key found.")

# --- Standardized Functions ---

def synthesize(
    text: str,
    voice_id: str,
    output_filename: str | None = None,
    instructions: str | None = None
    ) -> bool:
    """
    Synthesizes text using OpenAI TTS, optionally using persona instructions with
    compatible models (e.g., gpt-4o-mini-tts). This implementation uses a robust
    "Download-Then-Play" model.
    Returns True on success, False on failure.
    """
    if not OPENAI_API_KEY:
        print("Error: OpenAI API Key not configured. Cannot synthesize.")
        return False
    if not text or not text.strip():
        print("No dialogue text provided to synthesize.")
        return False
    if voice_id not in ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']:
        print(f"Warning: Unknown OpenAI voice_id '{voice_id}'. Using 'alloy' as default.")
        voice_id = 'alloy'

    print(f"\nSending dialogue to OpenAI TTS using Voice ID {voice_id}: '{text}'")
    if instructions and instructions.strip():
        instr_snippet = (instructions[:70] + '...') if len(instructions) > 70 else instructions
        print(f"  -> Using Persona Instructions: '{instr_snippet}'")


    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Requesting a raw WAV format is most reliable for direct playback with sounddevice/soundfile.
    response_format = "wav" if SOUND_LIBS_AVAILABLE else getattr(config, 'OPENAI_TTS_DEFAULT_FORMAT', 'mp3')
    model = getattr(config, 'OPENAI_TTS_MODEL', 'tts-1-hd')

    payload = {
        "model": model,
        "input": text,
        "voice": voice_id,
        "response_format": response_format,
    }

    # <<< THIS IS THE RESTORED LOGIC >>>
    # Add instructions to the payload if they are provided and the model supports them.
    if instructions and instructions.strip():
        payload["instructions"] = instructions.strip()
    # <<< END OF RESTORED LOGIC >>>


    audio_content = None
    try:
        # --- API Call (Stream Download to Memory) ---
        t_tts_api_start = time.perf_counter()
        print(f"    [TTS] Requesting synthesis from OpenAI API (Model: {model}, Format: {response_format})...")

        with requests.post(OPENAI_API_URL, headers=headers, json=payload, stream=True) as response:
            response.raise_for_status()
            
            audio_buffer = io.BytesIO()
            for chunk in response.iter_content(chunk_size=4096):
                audio_buffer.write(chunk)
            
            audio_buffer.seek(0)
            audio_content = audio_buffer.read()

        t_tts_api_end = time.perf_counter()
        api_duration = t_tts_api_end - t_tts_api_start
        print(f"    [Time] OpenAI TTS API Download Duration: {api_duration:.3f} seconds")

        if not audio_content:
            print("Error: Received no audio content from OpenAI.")
            return False

        # --- Playback Implementation ---
        played_successfully = False
        if SOUND_LIBS_AVAILABLE:
            try:
                audio_data, samplerate = sf.read(io.BytesIO(audio_content), dtype='float32')
                
                print(f"    [TTS] Starting playback ({samplerate} Hz, {audio_data.shape[1] if audio_data.ndim > 1 else 1} ch)...")
                sd.play(audio_data, samplerate, blocking=True)
                
                t_playback_end = time.perf_counter()
                playback_duration = t_playback_end - t_tts_api_end
                print(f"    [Time] Audio Playback Duration (Wall Time): {playback_duration:.3f} seconds")
                played_successfully = True

            except Exception as e:
                print(f"Error during audio playback: {type(e).__name__}: {e}")
                traceback.print_exc()
        else:
            print("Audio playback skipped (sounddevice/soundfile not available).")

        # --- Saving ---
        saved_successfully = False
        if output_filename:
            try:
                output_dir = os.path.dirname(output_filename)
                if output_dir and not os.path.exists(output_dir):
                     os.makedirs(output_dir, exist_ok=True)
                
                with open(output_filename, "wb") as out:
                    out.write(audio_content)
                print(f"Audio saved to: {output_filename}")
                saved_successfully = True
            except Exception as e:
                print(f"Error saving OpenAI TTS audio file '{output_filename}': {e}")
        
        return saved_successfully or (played_successfully and not output_filename)

    # --- Error Handling ---
    except requests.exceptions.RequestException as e:
        print(f"Error during OpenAI TTS API request: {e}")
        if e.response is not None:
            print(f"    Status Code: {e.response.status_code}")
            try:
                print(f"    Response Body: {e.response.json()}")
            except requests.exceptions.JSONDecodeError:
                print(f"    Response Body (non-JSON): {e.response.text}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred in synthesize function: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def get_voices() -> dict:
    """
    Returns available OpenAI voices in the standardized format.
    NOTE: OpenAI voices are fixed and do not have official gender classifications.
          Genders assigned here ('male'/'female') are based on common perception.
    """
    print("Fetching available voices from OpenAI TTS (hardcoded list)...")

    voices = {
        'alloy': 'male', 'echo': 'male', 'fable': 'male', 'onyx': 'male', 
        'nova': 'female', 'shimmer': 'female'
    }

    male_voices = []
    female_voices = []

    for voice_id, perceived_gender in voices.items():
        voice_name = voice_id.capitalize()
        voice_data = {"id": voice_id, "name": voice_name}
        if perceived_gender == "male":
            male_voices.append(voice_data)
        elif perceived_gender == "female":
            female_voices.append(voice_data)

    print(f"Found {len(male_voices)} perceived male voices and {len(female_voices)} perceived female voices.")
    return {"male": male_voices, "female": female_voices}

# --- Example Usage (Optional) ---
if __name__ == '__main__':
    print("\n--- OpenAI TTS Module Test ---")

    if not OPENAI_API_KEY:
        print("Cannot run test: OPENAI_API_KEY not set in config.py")
    else:
        # --- Test Synthesis with Instructions ---
        test_voice_id = 'fable'
        test_text = "As I say, if you're not all thumbs, you'll get out alive."
        test_instructions = "Speak as an old, weary storyteller recounting a dangerous memory."
        
        print(f"\nTesting synthesis with instructions using voice: {test_voice_id}")
        if SOUND_LIBS_AVAILABLE:
            success = synthesize(test_text, test_voice_id, instructions=test_instructions)
            print(f"Playback Test Result: {'Success' if success else 'Failed'}")
        else:
            print("Skipping playback test (sound libraries not available).")