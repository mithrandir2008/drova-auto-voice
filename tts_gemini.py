import os
import io
import time
import numpy as np
import threading
import traceback
from typing import Union, Dict, List

# Google Gemini API imports
import google.genai as genai
from google.genai import types # Essential for SpeechConfig, VoiceConfig, etc.

import config # Use config for API key and settings

# Optional: For audio playback directly (requires sounddevice, soundfile)
try:
    import sounddevice as sd
    import soundfile as sf
    SOUND_LIBS_AVAILABLE = True
except ImportError:
    print("Warning: 'sounddevice' or 'soundfile' not installed. Gemini TTS playback disabled.")
    SOUND_LIBS_AVAILABLE = False

# --- Initialize Client ---
gemini_client = None # Initialize to None

try:
    if not config.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY not found in .env file or environment variables. Gemini TTS module disabled.")
    
    # IMPORTANT: The 'google.generativeai' library exposes 'Client' directly.
    # If you get 'AttributeError: module 'google.generativeai' has no attribute 'Client'',
    # your 'google-generativeai' library is likely outdated.
    # Update with: pip install --upgrade google-generativeai
    gemini_client = genai.Client(api_key=config.GOOGLE_API_KEY)
    print("Gemini API client initialized successfully for TTS.")

except AttributeError as ae:
    # Specifically catch AttributeError for 'Client' and provide a direct solution
    print(f"Error initializing Gemini API client for TTS: {ae}")
    print("This often means your 'google-generativeai' library is outdated or improperly installed.")
    print("Please try updating it using: 'pip install --upgrade google-generativeai'")
    print("If the problem persists, try reinstalling: 'pip uninstall google-generativeai' then 'pip install google-generativeai'")
    # gemini_client remains None, so subsequent calls will fail gracefully
except Exception as e:
    # Catch any other unexpected errors during client initialization
    print(f"Error initializing Gemini API client for TTS: {e}")
    # gemini_client remains None

# --- Standardized Functions ---

def synthesize(
    text: str,
    voice_id: str,
    output_filename: Union[str, None] = None,
    instructions: Union[str, None] = None
    ) -> bool:
    """
    Synthesizes text using Gemini TTS.
    Plays audio using sounddevice or saves the audio.
    Returns True on success, False on failure.

    Args:
        text: The text to synthesize.
        voice_id: The Gemini TTS voice name (e.g., 'Kore', 'Puck').
        output_filename: Path to save the audio file. If None, audio is only played.
        instructions: Optional detailed persona instructions for the TTS voice.
                      These will be incorporated directly into the prompt.
    """
    if not gemini_client:
        print("Error: Gemini API client not initialized. Cannot synthesize.")
        return False
    if not text or not text.strip():
        print("No dialogue text provided to synthesize.")
        return False
    if not voice_id:
        print("Error: No Gemini TTS Voice Name (ID) provided.")
        return False

    # --- Construct the Prompt with Instructions ---
    tts_prompt = text.strip()
    if instructions and instructions.strip():
        # Gemini TTS instructions are part of the prompt
        # Example from docs: "Say cheerfully: Have a wonderful day!"
        tts_prompt = f"{instructions.strip()}: {text.strip()}"
        instr_snippet = (instructions[:70] + '...') if len(instructions) > 70 else instructions
        print(f"  -> Using Persona Instructions in prompt: '{instr_snippet}'")

    print(f"\nSending dialogue to Gemini TTS using Voice Name '{voice_id}': '{tts_prompt}'")

    # Determine model from config (it should be a Gemini 2.5 TTS model)
    gemini_tts_model = getattr(config, 'GEMINI_TTS_MODEL', 'gemini-2.5-flash-preview-tts')

    try:
        # --- Gemini API Call ---
        t_tts_api_start = time.perf_counter()
        print(f"    [TTS] Requesting synthesis from Gemini API (Model: {gemini_tts_model})...")

        response = gemini_client.models.generate_content(
            model=gemini_tts_model,
            contents=tts_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_id,
                        )
                    )
                ),
            )
        )

        t_tts_api_end = time.perf_counter()
        api_duration = t_tts_api_end - t_tts_api_start
        print(f"    [Time] Gemini TTS API Call Duration: {api_duration:.3f} seconds")

        if not response.candidates:
            safety_info = "N/A"
            block_reason = "Unknown"
            try:
                if response.prompt_feedback:
                    safety_info = getattr(response.prompt_feedback, 'safety_ratings', "N/A")
                    block_reason = getattr(response.prompt_feedback, 'block_reason', "Unknown")
            except Exception:
                pass # Ignore errors trying to get feedback details
            print(f"Error: Gemini TTS response blocked or empty. Reason: {block_reason}, Safety Ratings: {safety_info}")
            return False

        # Extract raw audio data (PCM)
        audio_content_bytes = response.candidates[0].content.parts[0].inline_data.data
        if not audio_content_bytes:
            print("Error: No audio data received from Gemini TTS API.")
            return False

        # --- Playback Implementation ---
        played_successfully = False
        playback_duration = 0.0
        # Gemini TTS models typically output 24000 Hz, 1-channel, 16-bit PCM.
        # We'll use these fixed values based on docs.
        samplerate = 24000
        channels = 1
        dtype = np.int16 # 16-bit signed integers

        if SOUND_LIBS_AVAILABLE and audio_content_bytes:
            playback_finished_event = threading.Event()
            current_frame = 0
            audio_data = None
            stream = None

            try:
                print(f"    [TTS] Decoding audio data (raw PCM, {samplerate} Hz, {channels} ch, dtype: {dtype})...")
                # Directly convert bytes to numpy array
                temp_audio_data = np.frombuffer(audio_content_bytes, dtype=dtype)
                audio_data = temp_audio_data.copy() # Make it writeable for fade-in

                if audio_data is None or len(audio_data) == 0:
                     print("Error: Failed to decode audio data for playback.")
                     raise ValueError("Empty or undecodable audio data")

                # --- ADD FADE-IN ---
                fade_duration_ms = 5
                fade_samples = int(samplerate * (fade_duration_ms / 1000.0))
                fade_samples = min(fade_samples, len(audio_data))

                if fade_samples > 0:
                    fade_curve = np.linspace(0.0, 1.0, fade_samples, dtype=audio_data.dtype)**2
                    if audio_data.ndim == 1: # Mono
                        # Ensure type conversion for multiplication and back
                        audio_data[:fade_samples] = (audio_data[:fade_samples].astype(np.float32) * fade_curve).astype(dtype)
                    elif audio_data.ndim > 1: # Multi-channel (unlikely for Gemini TTS current output)
                        audio_data[:fade_samples, :] = (audio_data[:fade_samples, :].astype(np.float32) * fade_curve[:, np.newaxis]).astype(dtype)
                # --- END FADE-IN ---

                print(f"    [TTS] Starting streaming playback ({samplerate} Hz, {channels} ch, dtype: {audio_data.dtype})...")

                def audio_callback(outdata, frames, time_info, status):
                    """Callback function for sounddevice stream."""
                    nonlocal current_frame
                    if status:
                        print(f"    [TTS Playback Status] {status}")
                    try:
                        chunk_size = min(len(audio_data) - current_frame, frames)
                        if chunk_size <= 0:
                            outdata[:] = 0
                            if not playback_finished_event.is_set(): playback_finished_event.set()
                            raise sd.CallbackStop # Normal termination
                        chunk = audio_data[current_frame : current_frame + chunk_size]

                        # Handle channel mapping for output
                        outdata_channels = outdata.shape[1]
                        if channels == 1 and outdata_channels == 1: outdata[:chunk_size, 0] = chunk
                        elif channels == 1 and outdata_channels > 1: outdata[:chunk_size, :] = chunk.reshape(-1, 1) # Expand mono to stereo/multi
                        elif channels > 1 and outdata_channels == 1: outdata[:chunk_size, 0] = chunk.mean(axis=1) # Mix multi to mono
                        elif channels == outdata_channels: outdata[:chunk_size] = chunk
                        else: # Mismatched channels fallback
                             print(f"    [Warning] Mismatched audio channels. Source: {channels}, Output: {outdata_channels}. Attempting mix/tile.")
                             if outdata_channels > channels:
                                 outdata[:chunk_size, :channels] = chunk; outdata[:chunk_size, channels:] = 0
                             else: outdata[:chunk_size, :] = chunk[:,:outdata_channels]

                        # Fill remaining buffer with silence if necessary
                        if chunk_size < frames:
                            outdata[chunk_size:] = 0
                            if current_frame + chunk_size >= len(audio_data):
                                if not playback_finished_event.is_set(): playback_finished_event.set()
                                raise sd.CallbackStop # Normal termination

                        current_frame += chunk_size
                    except sd.CallbackStop: # Handle CallbackStop separately
                        raise # Re-raise it so sounddevice handles it internally
                    except Exception as cb_e:
                        print(f"    [Error in audio_callback] {type(cb_e).__name__}: {cb_e}")
                        traceback.print_exc(); outdata[:] = 0
                        if not playback_finished_event.is_set(): playback_finished_event.set()
                        raise sd.CallbackStop # Stop stream on actual error

                t_playback_start = time.perf_counter()

                # Determine output channels based on default device capability if possible
                try:
                    device_info = sd.query_devices(kind='output')
                    output_channels = device_info.get('max_output_channels', channels)
                    if output_channels <= 0: output_channels = channels # Safety check
                except Exception as dev_e:
                    print(f"    [Warning] Failed to query output device info: {dev_e}. Defaulting to source channels ({channels}).")
                    output_channels = channels

                stream = sd.OutputStream(
                    samplerate=samplerate,
                    channels=output_channels,
                    dtype=audio_data.dtype,
                    callback=audio_callback)
                with stream:
                    timeout_seconds = (len(audio_data) / samplerate) + 10.0 # Generous timeout
                    if not playback_finished_event.wait(timeout=timeout_seconds):
                         print(f"    [Warning] Playback finished event timed out after {timeout_seconds:.1f}s. Stream might not have completed naturally.")
                         if stream.active:
                             try: stream.stop()
                             except Exception as stop_e: print(f"    Error stopping stream on timeout: {stop_e}")

                t_playback_end = time.perf_counter()
                playback_duration = t_playback_end - t_playback_start
                print(f"    [Time] Audio Playback Duration (Wall Time): {playback_duration:.3f} seconds")
                played_successfully = playback_finished_event.is_set()

            except sd.PortAudioError as pae:
                 print(f"PortAudio Error during playback setup or execution: {pae}")
                 traceback.print_exc()
                 if stream is not None: stream.close()
                 if not playback_finished_event.is_set(): playback_finished_event.set()
            except Exception as e:
                print(f"Error during streaming playback setup or execution: {type(e).__name__}: {e}")
                traceback.print_exc()
                if stream is not None and stream.active:
                    try: stream.stop(); stream.close()
                    except Exception as close_e: print(f"    Error stopping/closing audio stream on error: {close_e}")
                if not playback_finished_event.is_set():
                      playback_finished_event.set()
            finally: # Ensure the event is always set, even if other exceptions occur before wait()
                 if not playback_finished_event.is_set():
                      playback_finished_event.set()


        elif not SOUND_LIBS_AVAILABLE:
            print("Audio playback skipped (sounddevice/soundfile not available).")

        # --- Saving ---
        saved_successfully = False
        if output_filename:
            if audio_content_bytes:
                try:
                    # Save as WAV directly since Gemini TTS outputs PCM
                    if not output_filename.lower().endswith(('.wav')):
                        output_filename = output_filename + ".wav" # Ensure WAV extension
                        print(f"Adjusted output filename to: {output_filename} (Gemini TTS outputs WAV)")

                    output_dir = os.path.dirname(output_filename)
                    if output_dir and not os.path.exists(output_dir):
                         os.makedirs(output_dir, exist_ok=True)
                         print(f"Created output directory: {output_dir}")

                    # Use soundfile to write WAV for consistency, or wave module directly
                    # For simplicity and robust header writing, soundfile is better.
                    # Need to write the raw PCM with the correct headers (samplerate, channels, dtype)
                    sf.write(output_filename, audio_data, samplerate) # audio_data has already been converted to numpy array
                    print(f"Audio saved to: {output_filename}")
                    saved_successfully = True
                except Exception as e:
                    print(f"Error saving Gemini TTS audio file '{output_filename}': {e}")
                    traceback.print_exc()
            else:
                 print("Skipping save: No audio data received from API.")
        else:
             saved_successfully = played_successfully or (not SOUND_LIBS_AVAILABLE and bool(audio_content_bytes))

        return bool(audio_content_bytes) and (saved_successfully or (played_successfully and not output_filename))

    except Exception as e:
        print(f"An error occurred during Gemini TTS API call or main audio handling: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def get_voices() -> Dict[str, List[Dict[str, str]]]:
    """
    Returns available Gemini TTS voices in the standardized format.
    These are prebuilt voices. Gender is based on common perception.
    """
    print("Fetching available voices from Gemini TTS (hardcoded list)...")

    # List of voices from Gemini TTS documentation, with perceived genders.
    # THIS IS SUBJECTIVE and based on common perception/example usage.
    voices_data = [
        {"id": "Zephyr", "name": "Zephyr", "gender": "female"},    # Bright
        {"id": "Puck", "name": "Puck", "gender": "male"},          # Upbeat
        {"id": "Charon", "name": "Charon", "gender": "male"},      # Informative
        {"id": "Kore", "name": "Kore", "gender": "female"},        # Firm
        {"id": "Fenrir", "name": "Fenrir", "gender": "male"},      # Excitable
        {"id": "Leda", "name": "Leda", "gender": "female"},        # Youthful
        {"id": "Orus", "name": "Orus", "gender": "male"},          # Firm
        {"id": "Aoede", "name": "Aoede", "gender": "female"},      # Breezy
        {"id": "Callirrhoe", "name": "Callirrhoe", "gender": "female"}, # Easy-going
        {"id": "Autonoe", "name": "Autonoe", "gender": "female"},  # Bright
        {"id": "Enceladus", "name": "Enceladus", "gender": "male"},# Breathy
        {"id": "Iapetus", "name": "Iapetus", "gender": "male"},    # Clear
        {"id": "Umbriel", "name": "Umbriel", "gender": "male"},    # Easy-going
        {"id": "Algieba", "name": "Algieba", "gender": "male"},    # Smooth
        {"id": "Despina", "name": "Despina", "gender": "female"},  # Smooth
        {"id": "Erinome", "name": "Erinome", "gender": "female"},  # Clear
        {"id": "Algenib", "name": "Algenib", "gender": "male"},    # Gravelly
        {"id": "Rasalgethi", "name": "Rasalgethi", "gender": "male"}, # Informative
        {"id": "Laomedeia", "name": "Laomedeia", "gender": "female"}, # Upbeat
        {"id": "Achernar", "name": "Achernar", "gender": "male"},  # Soft
        {"id": "Alnilam", "name": "Alnilam", "gender": "male"},    # Firm
        {"id": "Schedar", "name": "Schedar", "gender": "male"},    # Even
        {"id": "Gacrux", "name": "Gacrux", "gender": "male"},      # Mature
        {"id": "Pulcherrima", "name": "Pulcherrima", "gender": "female"}, # Forward
        {"id": "Achird", "name": "Achird", "gender": "male"},      # Friendly
        {"id": "Zubenelgenubi", "name": "Zubenelgenubi", "gender": "male"}, # Casual
        {"id": "Vindemiatrix", "name": "Vindemiatrix", "gender": "female"}, # Gentle
        {"id": "Sadachbia", "name": "Sadachbia", "gender": "male"},# Lively
        {"id": "Sadaltager", "name": "Sadaltager", "gender": "male"}, # Knowledgeable
        {"id": "Sulafat", "name": "Sulafat", "gender": "female"},  # Warm
    ]

    male_voices = []
    female_voices = []

    for voice in voices_data:
        voice_entry = {"id": voice["id"], "name": voice["name"]}
        if voice["gender"] == "male":
            male_voices.append(voice_entry)
        elif voice["gender"] == "female":
            female_voices.append(voice_entry)

    print(f"Found {len(male_voices)} perceived male voices and {len(female_voices)} perceived female voices for Gemini TTS.")
    return {"male": male_voices, "female": female_voices}

# --- Example Usage (Optional) ---
if __name__ == '__main__':
    print("\n--- Gemini TTS Module Test ---")

    # This requires GOOGLE_API_KEY to be set in your .env or environment
    # and sounddevice/soundfile to be installed for playback.
    # Set GOOGLE_API_KEY="YOUR_API_KEY" in .env
    # pip install python-dotenv google-generativeai sounddevice soundfile numpy

    # Temporarily set config values for testing
    import dotenv
    dotenv.load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        print("Cannot run test: GOOGLE_API_KEY not set in .env")
        exit(1)

    # Set up dummy config attributes if running standalone
    class MockConfig:
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
        TARGET_SAMPLE_RATE = 48000 # Your desired target, but model outputs 24000
        DEFAULT_FALLBACK_VOICE_ID = "Kore" # A default Gemini voice

    config = MockConfig() # Overwrite for this test block

    available_voices = get_voices()
    print("\nAvailable Voices:")
    print("Male:", available_voices.get('male', []))
    print("Female:", available_voices.get('female', []))

    # Test Synthesis + Playback
    if available_voices['female']:
        test_voice_id = "Kore" # A common female voice
        test_text = "Hello from Gemini! This is a test using the Kore voice."
        test_instructions = "Say cheerfully"
        print(f"\nTesting synthesis and playback with voice: {test_voice_id}")
        if SOUND_LIBS_AVAILABLE:
            success = synthesize(test_text, test_voice_id, instructions=test_instructions)
            print(f"Playback Test Result: {'Success' if success else 'Failed'}")
        else:
            print("Skipping playback test (sound libraries not available).")

    # Test Synthesis + Save
    if available_voices['male']:
        test_voice_id_save = "Puck" # A common male voice
        test_text_save = "This audio should be saved to a file named test_gemini_speech.wav. Please speak clearly."
        output_file = "test_gemini_speech.wav"
        save_instructions = "Speak in a calm and clear voice"
        print(f"\nTesting synthesis and saving with voice: {test_voice_id_save}")

        success_save = synthesize(test_text_save, test_voice_id_save, output_filename=output_file, instructions=save_instructions)
        print(f"Saving Test Result: {'Success' if success_save else 'Failed'}")
        if success_save:
            print(f"Check for the file: {os.path.abspath(output_file)}")
    else:
        print("\nSkipping save test (no male voices found?).")