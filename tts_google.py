import os
from google.cloud import texttospeech
import config
import io
import time
import numpy as np # Need numpy for audio data manipulation
import threading # Need threading for event synchronization
import traceback # For detailed error printing

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
    Synthesizes plain text using Google TTS. Plays audio using sounddevice's
    OutputStream for smooth playback after API call completion.
    Optionally saves the audio.
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

    print(f"\nSending dialogue text to Google TTS using Voice Name {voice_id}: '{text}'")

    extracted_language_code = config.GOOGLE_TTS_LANGUAGE_CODE
    try:
        # Attempt to parse language code from voice ID (e.g., "en-US-Wavenet-D")
        parts = voice_id.split('-')
        if len(parts) >= 2:
            parsed_code = f"{parts[0]}-{parts[1]}"
            # Basic validation for xx-XX format
            if len(parsed_code) == 5 and parsed_code[2] == '-' and parsed_code[:2].isalpha() and parsed_code[3:].isalpha():
                 extracted_language_code = parsed_code
            else:
                 print(f"Warning: Could not reliably parse standard language code format (xx-XX) from start of voice ID '{voice_id}'. Using default '{extracted_language_code}'.")
        else:
            print(f"Warning: Voice ID '{voice_id}' format unexpected. Using default '{extracted_language_code}'.")
    except Exception as e:
        print(f"Warning: Error parsing language code from voice ID '{voice_id}': {e}. Using default '{extracted_language_code}'.")


    try:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=extracted_language_code, name=voice_id)
        target_sample_rate = config.TARGET_SAMPLE_RATE # Or your desired rate

        # Request LINEAR16 if playback libs are available, otherwise use configured encoding
        requested_encoding = texttospeech.AudioEncoding.LINEAR16 if SOUND_LIBS_AVAILABLE else getattr(texttospeech.AudioEncoding, config.GOOGLE_TTS_AUDIO_ENCODING, texttospeech.AudioEncoding.MP3)

        audio_config = texttospeech.AudioConfig(
            audio_encoding=requested_encoding,
            sample_rate_hertz=target_sample_rate)

        t_tts_api_start = time.perf_counter()
        print("    [TTS] Requesting synthesis from Google API...")
        response = google_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config)
        t_tts_api_end = time.perf_counter()
        api_duration = t_tts_api_end - t_tts_api_start
        print(f"    [Time] Google TTS API Call Duration: {api_duration:.3f} seconds")

        audio_content = response.audio_content

        # --- Streaming Playback Implementation ---
        played_successfully = False
        playback_duration = 0.0
        if SOUND_LIBS_AVAILABLE and audio_content:
            playback_finished_event = threading.Event()
            current_frame = 0
            audio_data = None
            samplerate = 0
            stream = None # Define stream variable outside try

            try:
                # Read entire audio data into memory first (as API doesn't stream response)
                # Check actual encoding received, as API might return something different
                actual_encoding = audio_config.audio_encoding # Ideally check response if possible, using requested for now
                # print(f"    [Debug] Requested encoding: {requested_encoding}, Assuming actual: {actual_encoding}") # Optional debug

                if actual_encoding == texttospeech.AudioEncoding.LINEAR16:
                     # Assuming 16-bit signed integers based on LINEAR16
                     # Create a temporary read-only view first
                     temp_audio_data = np.frombuffer(audio_content, dtype=np.int16)
                     samplerate = audio_config.sample_rate_hertz # Use rate from request
                     # Create a writeable copy for modifications (like fade-in)
                     audio_data = temp_audio_data.copy() # <<<--- CREATE WRITEABLE COPY
                     # Note: Google LINEAR16 is typically mono. If stereo is ever returned, shaping might be needed:
                     # if audio_data.shape[0] % 2 == 0: # Basic check
                     #     try: audio_data = audio_data.reshape(-1, 2)
                     #     except ValueError: pass # Keep as mono if reshape fails
                else: # Fallback to reading MP3 or other encoded formats using soundfile
                    print(f"    [TTS] Decoding audio format (assuming non-LINEAR16)...")
                    # soundfile reads into float format by default unless dtype specified
                    temp_audio_data, samplerate = sf.read(io.BytesIO(audio_content))
                    # Create a writeable copy
                    audio_data = temp_audio_data.copy() # <<<--- CREATE WRITEABLE COPY
                    # Use the samplerate reported by soundfile
                    if samplerate != audio_config.sample_rate_hertz:
                         print(f"    [Warning] Samplerate from decoded file ({samplerate} Hz) differs from requested rate ({audio_config.sample_rate_hertz} Hz). Using decoded rate.")


                # Optional: Check if the copy is writeable (for debugging)
                # print(f"    [Debug] Audio data is writeable: {audio_data.flags.writeable}")

                if audio_data is None or len(audio_data) == 0:
                     print("Error: Failed to decode audio data for playback.")
                     raise ValueError("Empty or undecodable audio data") # Prevent proceeding

                # ---> ADD FADE-IN (Operates on the writeable copy) <---
                fade_duration_ms = 5  # Adjust fade duration (e.g., 3-10 ms)
                fade_samples = int(samplerate * (fade_duration_ms / 1000.0))
                fade_samples = min(fade_samples, len(audio_data)) # Ensure fade is not longer than audio

                if fade_samples > 0:
                    print(f"Applying {fade_duration_ms}ms fade-in ({fade_samples} samples)...")
                    # Ensure fade_curve has the same dtype as audio_data or can be safely cast
                    fade_curve = np.linspace(0.0, 1.0, fade_samples, dtype=audio_data.dtype)**2 # Quadratic fade-in

                    # Apply the fade using in-place multiplication
                    if audio_data.ndim == 1: # Mono
                        audio_data[:fade_samples] *= fade_curve
                    elif audio_data.ndim > 1: # Stereo or more channels
                        # Ensure fade_curve is broadcastable (needs extra dimension)
                        audio_data[:fade_samples, :] *= fade_curve[:, np.newaxis]
                    else:
                         print("Warning: audio_data has unexpected dimensions for fade-in.")
                # ---> END FADE-IN <---


                channels = audio_data.shape[1] if audio_data.ndim > 1 else 1
                print(f"    [TTS] Starting streaming playback ({samplerate} Hz, {channels} ch, dtype: {audio_data.dtype})...")

                def audio_callback(outdata, frames, time_info, status):
                    """Callback function for sounddevice stream."""
                    nonlocal current_frame
                    if status:
                        print(f"    [TTS Playback Status] {status}")

                    try:
                        chunk_size = min(len(audio_data) - current_frame, frames)
                        if chunk_size <= 0:
                            print("    [TTS Playback] Reached end of data (chunk_size <= 0).")
                            outdata[:] = 0 # Fill buffer with silence
                            playback_finished_event.set()
                            raise sd.CallbackStop

                        chunk = audio_data[current_frame : current_frame + chunk_size]

                        # --- Shape Handling Logic ---
                        outdata_channels = outdata.shape[1] # Channels expected by the output buffer

                        # Fill the valid part of the buffer first
                        if channels == 1 and outdata_channels == 1:
                            outdata[:chunk_size, 0] = chunk # Assign mono to mono column
                        elif channels == 1 and outdata_channels > 1:
                             # Tile mono chunk to multiple output channels
                             outdata[:chunk_size, :] = chunk.reshape(-1, 1)
                        elif channels > 1 and outdata_channels == 1:
                             # Mix down multi-channel chunk to mono output
                             outdata[:chunk_size, 0] = chunk.mean(axis=1)
                        elif channels == outdata_channels:
                             # Direct copy (e.g., stereo->stereo)
                             outdata[:chunk_size] = chunk
                        else: # Mismatched channels (more complex case)
                             print(f"    [Warning] Mismatched audio channels. Source: {channels}, Output: {outdata_channels}. Attempting mix/tile.")
                             # Simple mix/tile fallback (might not sound ideal)
                             if outdata_channels > channels: # Tile source to output
                                 outdata[:chunk_size, :channels] = chunk
                                 outdata[:chunk_size, channels:] = 0 # Silence extra channels
                             else: # Mix source down to output
                                 outdata[:chunk_size, :] = chunk[:,:outdata_channels] # Take first output_channels

                        # Fill remaining buffer with silence if chunk was smaller than frames
                        if chunk_size < frames:
                            outdata[chunk_size:] = 0
                            # Signal end only when the last actual data is sent
                            if current_frame + chunk_size >= len(audio_data):
                                print("    [TTS Playback] Reached end of data (chunk_size < frames).")
                                playback_finished_event.set()
                                raise sd.CallbackStop

                        current_frame += chunk_size
                        # --- End Shape Handling ---

                    except Exception as cb_e:
                        print(f"    [Error in audio_callback] {type(cb_e).__name__}: {cb_e}")
                        traceback.print_exc()
                        outdata[:] = 0 # Silence on error
                        playback_finished_event.set() # Ensure main thread isn't blocked
                        raise sd.CallbackStop # Stop the stream

                t_playback_start = time.perf_counter()

                # Create and start the stream
                # Determine output channels based on default device capability if possible
                try:
                    device_info = sd.query_devices(kind='output')
                    # Use device's max channels if available, else match source audio
                    output_channels = device_info.get('max_output_channels', channels)
                     # Safety check: don't request 0 channels
                    if output_channels <= 0:
                         print(f"    [Warning] Device query returned invalid channels ({output_channels}). Defaulting to source channels ({channels}).")
                         output_channels = channels
                    print(f"    [SoundDevice] Using output device: {sd.query_devices(kind='output')['name']} with {output_channels} channels.")

                except Exception as dev_e:
                    print(f"    [Warning] Failed to query output device info: {dev_e}. Defaulting to source channels ({channels}).")
                    output_channels = channels # Fallback if device query fails

                stream = sd.OutputStream(
                    samplerate=samplerate,
                    channels=output_channels, # Use queried/fallback output channels
                    dtype=audio_data.dtype, # Use the actual dtype of the loaded data
                    callback=audio_callback)
                with stream:
                    # Wait for the callback to signal completion (or error)
                    if not playback_finished_event.wait(timeout=len(audio_data)/samplerate + 5.0): # Add timeout buffer
                         print("    [Warning] Playback finished event timed out. Stream might not have completed naturally.")
                         # Ensure stream is stopped if timeout occurs
                         if stream.active:
                             try: stream.stop()
                             except Exception as stop_e: print(f"    Error stopping stream on timeout: {stop_e}")

                t_playback_end = time.perf_counter()
                playback_duration = t_playback_end - t_playback_start
                # Note: playback_duration measures wall time, not necessarily audio length
                print(f"    [Time] Audio Playback Duration (Wall Time): {playback_duration:.3f} seconds")
                played_successfully = playback_finished_event.is_set() # Consider successful if event was set

            except sd.PortAudioError as pae:
                 print(f"PortAudio Error during playback setup or execution: {pae}")
                 traceback.print_exc()
                 if stream is not None: stream.close() # Close on PortAudio error
                 playback_finished_event.set() # Ensure wait() doesn't block
            except Exception as e:
                print(f"Error during streaming playback setup or execution: {type(e).__name__}: {e}")
                traceback.print_exc() # Print full traceback
                if stream is not None and stream.active:
                    try:
                        stream.stop()
                        stream.close() # Ensure stream resources are released on error
                    except Exception as close_e:
                         print(f"    Error stopping/closing audio stream on error: {close_e}")
                playback_finished_event.set() # Ensure wait() doesn't block forever on error
            finally:
                 # Ensure event is set if error happened before wait()
                 if not playback_finished_event.is_set():
                      playback_finished_event.set()


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
                    print(f"Error saving Google TTS audio file '{output_filename}': {e}")
                    traceback.print_exc()
            else:
                 print("Skipping save: No audio data received from API.")
        else:
             # If no output filename, success depends on playback if libs available,
             # or just getting audio data if libs aren't available.
             saved_successfully = played_successfully or (not SOUND_LIBS_AVAILABLE and bool(audio_content))


        # Return True if we got audio data AND (it was saved OR (it was played successfully AND no save was requested))
        return bool(audio_content) and (saved_successfully or (played_successfully and not output_filename))


    except Exception as e:
        print(f"Error during Google TTS API call or main audio handling: {type(e).__name__}: {e}")
        traceback.print_exc()
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