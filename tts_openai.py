import os
import requests # Need requests for HTTP calls
import config
import io
import time
import numpy as np # Need numpy for audio data manipulation
import threading # Need threading for event synchronization
import traceback # For detailed error printing

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
    # You could raise an error here or just let functions fail later
else:
    print("OpenAI API Key found.")

# --- Standardized Functions ---

def synthesize(text: str, voice_id: str, output_filename: str | None = None) -> bool:
    """
    Synthesizes plain text using OpenAI TTS. Plays audio using sounddevice's
    OutputStream for smooth playback after API call completion.
    Optionally saves the audio.
    Returns True on success, False on failure.

    Args:
        text: The text to synthesize.
        voice_id: The OpenAI voice to use (e.g., 'alloy', 'echo', 'nova').
        output_filename: Path to save the audio file. If None, audio is only played.
    """
    if not OPENAI_API_KEY:
        print("Error: OpenAI API Key not configured. Cannot synthesize.")
        return False
    if not text or not text.strip():
        print("No dialogue text provided to synthesize.")
        return False
    if not voice_id:
        print("Error: No OpenAI TTS Voice ID provided.")
        return False
    if voice_id not in ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']:
        print(f"Warning: Unknown OpenAI voice_id '{voice_id}'. Using 'alloy' as default.")
        voice_id = 'alloy' # Or handle as error if preferred

    print(f"\nSending dialogue text to OpenAI TTS using Voice ID {voice_id}: '{text}'")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    # Prefer WAV for direct playback if libs are available, easier decoding.
    # Otherwise use MP3 or format from config. OpenAI default is mp3.
    # WAV or PCM might be necessary for precise sample rate control if needed,
    # but soundfile can handle mp3, flac etc. Let's try WAV for playback.
    response_format = "wav" if SOUND_LIBS_AVAILABLE else getattr(config, 'OPENAI_TTS_OUTPUT_FORMAT', 'mp3')

    payload = {
        "model": getattr(config, 'OPENAI_TTS_MODEL', 'tts-1'), # Default to tts-1 if not in config
        "input": text,
        "voice": voice_id,
        "response_format": response_format,
        # "speed": 1.0 # Optional speed control (0.25 to 4.0)
    }

    # Note: OpenAI's sample rate is fixed based on model/format (often 24kHz).
    # config.TARGET_SAMPLE_RATE is not directly sent, but used for comparison/info.
    target_sample_rate = getattr(config, 'TARGET_SAMPLE_RATE', 24000) # Default to 24k if not set


    try:
        t_tts_api_start = time.perf_counter()
        print(f"    [TTS] Requesting synthesis from OpenAI API (Model: {payload['model']}, Format: {response_format})...")
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
        t_tts_api_end = time.perf_counter()
        api_duration = t_tts_api_end - t_tts_api_start
        print(f"    [Time] OpenAI TTS API Call Duration: {api_duration:.3f} seconds")

        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        audio_content = response.content

        # --- Streaming Playback Implementation ---
        played_successfully = False
        playback_duration = 0.0
        if SOUND_LIBS_AVAILABLE and audio_content:
            playback_finished_event = threading.Event()
            current_frame = 0
            audio_data = None
            samplerate = 0 # Will be determined by sf.read
            stream = None # Define stream variable outside try

            try:
                # Use soundfile to read the audio data (handles various formats like wav, mp3, flac)
                # Read directly into float32 format, which is widely supported by sounddevice
                print(f"    [TTS] Decoding audio format ({response_format}) into float32...")
                temp_audio_data, samplerate = sf.read(io.BytesIO(audio_content), dtype='float32')

                # Create a writeable copy for modifications (like fade-in)
                audio_data = temp_audio_data.copy()

                if samplerate != target_sample_rate:
                     print(f"    [Info] Actual audio samplerate ({samplerate} Hz) differs from target ({target_sample_rate} Hz). Using actual rate for playback.")

                # Optional: Check if the copy is writeable (for debugging)
                # print(f"    [Debug] Audio data is writeable: {audio_data.flags.writeable}")

                if audio_data is None or len(audio_data) == 0:
                     print("Error: Failed to decode audio data for playback.")
                     raise ValueError("Empty or undecodable audio data")

                # ---> ADD FADE-IN (Operates on the writeable copy) <---
                fade_duration_ms = 5  # Adjust fade duration
                fade_samples = int(samplerate * (fade_duration_ms / 1000.0))
                fade_samples = min(fade_samples, len(audio_data))

                if fade_samples > 0:
                    print(f"Applying {fade_duration_ms}ms fade-in ({fade_samples} samples)...")
                    fade_curve = np.linspace(0.0, 1.0, fade_samples, dtype=audio_data.dtype)**2 # Quadratic

                    # Apply the fade using in-place multiplication
                    if audio_data.ndim == 1: # Mono
                        audio_data[:fade_samples] *= fade_curve
                    elif audio_data.ndim > 1: # Stereo or more channels
                        audio_data[:fade_samples, :] *= fade_curve[:, np.newaxis]
                    else:
                         print("Warning: audio_data has unexpected dimensions for fade-in.")
                # ---> END FADE-IN <---

                channels = audio_data.shape[1] if audio_data.ndim > 1 else 1
                print(f"    [TTS] Starting streaming playback ({samplerate} Hz, {channels} ch, dtype: {audio_data.dtype})...")

                # --- Identical audio_callback function from tts_google.py ---
                def audio_callback(outdata, frames, time_info, status):
                    """Callback function for sounddevice stream."""
                    nonlocal current_frame
                    if status:
                        print(f"    [TTS Playback Status] {status}")

                    try:
                        chunk_size = min(len(audio_data) - current_frame, frames)
                        if chunk_size <= 0:
                            # print("    [TTS Playback] Reached end of data (chunk_size <= 0).") # Debug
                            outdata[:] = 0 # Fill buffer with silence
                            if not playback_finished_event.is_set(): playback_finished_event.set()
                            raise sd.CallbackStop

                        chunk = audio_data[current_frame : current_frame + chunk_size]

                        # --- Shape Handling Logic ---
                        outdata_channels = outdata.shape[1] # Channels expected by the output buffer

                        # Fill the valid part of the buffer first
                        if channels == 1 and outdata_channels == 1:
                            outdata[:chunk_size, 0] = chunk
                        elif channels == 1 and outdata_channels > 1:
                            outdata[:chunk_size, :] = chunk.reshape(-1, 1)
                        elif channels > 1 and outdata_channels == 1:
                            outdata[:chunk_size, 0] = chunk.mean(axis=1)
                        elif channels == outdata_channels:
                            outdata[:chunk_size] = chunk
                        else: # Mismatched channels
                            print(f"    [Warning] Mismatched audio channels. Source: {channels}, Output: {outdata_channels}. Attempting mix/tile.")
                            if outdata_channels > channels:
                                outdata[:chunk_size, :channels] = chunk
                                outdata[:chunk_size, channels:] = 0
                            else:
                                outdata[:chunk_size, :] = chunk[:,:outdata_channels]

                        # Fill remaining buffer with silence if chunk was smaller than frames
                        if chunk_size < frames:
                            outdata[chunk_size:] = 0
                            # Signal end only when the last actual data is sent
                            if current_frame + chunk_size >= len(audio_data):
                                # print("    [TTS Playback] Reached end of data (chunk_size < frames).") # Debug
                                if not playback_finished_event.is_set(): playback_finished_event.set()
                                raise sd.CallbackStop

                        current_frame += chunk_size
                        # --- End Shape Handling ---

                    except Exception as cb_e:
                        print(f"    [Error in audio_callback] {type(cb_e).__name__}: {cb_e}")
                        traceback.print_exc()
                        outdata[:] = 0 # Silence on error
                        if not playback_finished_event.is_set(): playback_finished_event.set()
                        raise sd.CallbackStop # Stop the stream

                t_playback_start = time.perf_counter()

                # Create and start the stream
                try:
                    device_info = sd.query_devices(kind='output')
                    output_channels = device_info.get('max_output_channels', channels)
                    if output_channels <= 0:
                        print(f"    [Warning] Device query returned invalid channels ({output_channels}). Defaulting to source channels ({channels}).")
                        output_channels = channels
                    print(f"    [SoundDevice] Using output device: {sd.query_devices(kind='output')['name']} with {output_channels} channels.")
                except Exception as dev_e:
                    print(f"    [Warning] Failed to query output device info: {dev_e}. Defaulting to source channels ({channels}).")
                    output_channels = channels

                stream = sd.OutputStream(
                    samplerate=samplerate,
                    channels=output_channels,
                    dtype=audio_data.dtype, # Use dtype from loaded data
                    callback=audio_callback)
                with stream:
                     # Timeout slightly longer than expected audio duration
                    timeout_seconds = (len(audio_data) / samplerate) + 5.0
                    if not playback_finished_event.wait(timeout=timeout_seconds):
                         print(f"    [Warning] Playback finished event timed out after {timeout_seconds:.1f}s. Stream might not have completed naturally.")
                         if stream.active:
                             try: stream.stop()
                             except Exception as stop_e: print(f"    Error stopping stream on timeout: {stop_e}")

                t_playback_end = time.perf_counter()
                playback_duration = t_playback_end - t_playback_start
                print(f"    [Time] Audio Playback Duration (Wall Time): {playback_duration:.3f} seconds")
                played_successfully = playback_finished_event.is_set() # Consider successful if event was set

            except sd.PortAudioError as pae:
                 print(f"PortAudio Error during playback setup or execution: {pae}")
                 traceback.print_exc()
                 if stream is not None: stream.close()
                 if not playback_finished_event.is_set(): playback_finished_event.set()
            except Exception as e:
                print(f"Error during streaming playback setup or execution: {type(e).__name__}: {e}")
                traceback.print_exc()
                if stream is not None and stream.active:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception as close_e:
                         print(f"    Error stopping/closing audio stream on error: {close_e}")
                if not playback_finished_event.is_set(): playback_finished_event.set()
            finally:
                 if not playback_finished_event.is_set():
                      playback_finished_event.set() # Ensure main thread never blocks indefinitely


        elif not SOUND_LIBS_AVAILABLE:
            print("Audio playback skipped (sounddevice/soundfile not available).")
        elif not audio_content:
             print("Skipping playback: No audio content received from API.")

        # --- Saving ---
        saved_successfully = False
        if output_filename:
            if audio_content:
                try:
                    # Save the original audio_content bytes received from API
                    output_dir = os.path.dirname(output_filename)
                    if output_dir and not os.path.exists(output_dir):
                         os.makedirs(output_dir, exist_ok=True)
                         print(f"Created output directory: {output_dir}")
                    with open(output_filename, "wb") as out:
                        out.write(audio_content)
                    print(f"Audio saved to: {output_filename}")
                    saved_successfully = True
                except Exception as e:
                    print(f"Error saving OpenAI TTS audio file '{output_filename}': {e}")
                    traceback.print_exc()
            else:
                 print("Skipping save: No audio data received from API.")
        else:
             saved_successfully = played_successfully or (not SOUND_LIBS_AVAILABLE and bool(audio_content))

        # Return True if we got audio data AND (it was saved OR (it was played successfully AND no save was requested))
        return bool(audio_content) and (saved_successfully or (played_successfully and not output_filename))

    except requests.exceptions.RequestException as e:
        print(f"Error during OpenAI TTS API request: {e}")
        if e.response is not None:
            print(f"    Status Code: {e.response.status_code}")
            try:
                print(f"    Response Body: {e.response.json()}") # Show error details from OpenAI
            except requests.exceptions.JSONDecodeError:
                print(f"    Response Body: {e.response.text}") # Show raw text if not JSON
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

def get_voices() -> dict:
    """
    Returns available OpenAI voices in the standardized format.
    NOTE: OpenAI voices are fixed and do not have official gender classifications.
          Genders assigned here ('male'/'female') are based on common perception
          and may not match all listeners' interpretations.
    """
    print("Fetching available voices from OpenAI TTS (hardcoded list)...")

    # Mapping based on perceived gender – THIS IS SUBJECTIVE!
    voices = {
        "alloy": "male",     # Neutral/robotic tone, often perceived as male
        "ash": "male",       # Expressive, often perceived as male
        "ballad": "male",    # Deep and dramatic, often perceived as male
        "coral": "female",   # Warm and expressive, often perceived as female
        "echo": "male",      # Friendly and engaging, often perceived as male
        "fable": "male",     # British accent, often perceived as male
        "nova": "female",    # Bright and energetic, often perceived as female
        "onyx": "male",      # Deep and resonant, often perceived as male
        "sage": "female",    # Calm and soothing, often perceived as female
        "shimmer": "female", # Light and airy, often perceived as female
        "verse": "female",   # Expressive and melodic, often perceived as female
    }

    male_voices = []
    female_voices = []

    for voice_id, perceived_gender in voices.items():
        # Capitalize name for display
        voice_name = voice_id.capitalize()
        voice_data = {"id": voice_id, "name": voice_name}

        if perceived_gender == "male":
            male_voices.append(voice_data)
        elif perceived_gender == "female":
            female_voices.append(voice_data)
        # else: # If we had an 'unknown' category
        #    unknown_voices.append(voice_data)

    print(f"Found {len(male_voices)} perceived male voices and {len(female_voices)} perceived female voices.")
    return {"male": male_voices, "female": female_voices}

# --- Example Usage (Optional) ---
if __name__ == '__main__':
    print("\n--- OpenAI TTS Module Test ---")

    if not OPENAI_API_KEY:
        print("Cannot run test: OPENAI_API_KEY not set in config.py")
    else:
        available_voices = get_voices()
        print("\nAvailable Voices:")
        print("Male:", available_voices.get('male', []))
        print("Female:", available_voices.get('female', []))

        # --- Test Synthesis + Playback ---
        if available_voices['female']:
             test_voice_id = available_voices['female'][0]['id'] # Use first female voice (e.g., Nova)
             test_text = "Hello from OpenAI! This is a test using the Nova voice."
             print(f"\nTesting synthesis and playback with voice: {test_voice_id}")
             if SOUND_LIBS_AVAILABLE:
                 success = synthesize(test_text, test_voice_id)
                 print(f"Playback Test Result: {'Success' if success else 'Failed'}")
             else:
                 print("Skipping playback test (sound libraries not available).")

        # --- Test Synthesis + Save ---
        if available_voices['male']:
            test_voice_id_save = available_voices['male'][0]['id'] # Use first male voice (e.g., Alloy)
            test_text_save = "This audio should be saved to a file named test_openai_speech.mp3"
            output_file = "test_openai_speech.mp3" # Will be saved as mp3 regardless of playback preference
            print(f"\nTesting synthesis and saving with voice: {test_voice_id_save}")

            # Temporarily override response format for saving if needed (optional)
            # If you specifically want to save as mp3 even if playback uses wav:
            original_format = getattr(config, 'OPENAI_TTS_OUTPUT_FORMAT', 'mp3')
            config.OPENAI_TTS_OUTPUT_FORMAT = 'mp3' # Force mp3 for saving test
            # Or, more robustly, modify the synthesize function to accept a save_format parameter

            success_save = synthesize(test_text_save, test_voice_id_save, output_filename=output_file)
            print(f"Saving Test Result: {'Success' if success_save else 'Failed'}")
            if success_save:
                print(f"Check for the file: {os.path.abspath(output_file)}")

            # Restore config if changed
            # config.OPENAI_TTS_OUTPUT_FORMAT = original_format

        else:
             print("\nSkipping save test (no male voices found?).")
