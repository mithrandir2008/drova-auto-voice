import os
import io
import time
import numpy as np
import threading
import traceback
import queue
from typing import Union, Dict, List

# Google Gemini API imports
import google.genai as genai
from google.genai import types

import config

# --- New Debugging Flag ---
# Set to True to get detailed logs about audio buffer status, False for normal operation.
DEBUG_AUDIO = False

try:
    import sounddevice as sd
    import soundfile as sf
    SOUND_LIBS_AVAILABLE = True
except ImportError:
    print("Warning: 'sounddevice' or 'soundfile' not installed. Gemini TTS playback disabled.")
    SOUND_LIBS_AVAILABLE = False

gemini_client = None

try:
    if not config.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY not found in .env file or environment variables. Gemini TTS module disabled.")
    
    gemini_client = genai.Client(api_key=config.GOOGLE_API_KEY)
    print("Gemini API client initialized successfully for TTS.")

except AttributeError as ae:
    print(f"Error initializing Gemini API client for TTS: {ae}")
    # ... (rest of init is unchanged)
except Exception as e:
    print(f"Error initializing Gemini API client for TTS: {e}")

GEMINI_TTS_SAMPLERATE = 24000
GEMINI_TTS_CHANNELS = 1
GEMINI_TTS_DTYPE = np.int16

def synthesize(
    text: str,
    voice_id: str,
    output_filename: Union[str, None] = None,
    instructions: Union[str, None] = None
    ) -> bool:
    if not gemini_client:
        print("Error: Gemini API client not initialized. Cannot synthesize.")
        return False
    if not text or not text.strip():
        print("No dialogue text provided to synthesize.")
        return False
    if not voice_id:
        print("Error: No Gemini TTS Voice Name (ID) provided.")
        return False

    gemini_tts_model = getattr(config, 'GEMINI_TTS_MODEL', 'models/tts-1')

    audio_queue = queue.Queue(maxsize=100) # Give queue a max size for safety
    all_audio_bytes_for_save = []
    producer_started_streaming_event = threading.Event()

    def _audio_producer_thread_func(
        # ... (all args are unchanged)
        producer_text: str, 
        producer_voice_id: str, 
        producer_instructions: Union[str, None], 
        producer_model: str,
        producer_audio_queue: queue.Queue, 
        producer_all_audio_bytes_for_save: List[bytes], 
        producer_save_enabled: bool,
        producer_started_streaming_event: threading.Event
    ):
        try:
            # ... (prompt creation is unchanged)
            producer_tts_prompt = producer_text.strip()
            if producer_instructions and producer_instructions.strip():
                producer_tts_prompt = f"{producer_instructions.strip()}: {producer_text.strip()}"
                instr_snippet = (producer_instructions[:70] + '...') if len(producer_instructions) > 70 else producer_instructions
                print(f"  -> Using Persona Instructions in prompt: '{instr_snippet}' (in producer thread)")

            print(f"    [TTS] Requesting synthesis from Gemini API (Model: {producer_model}, using streamGenerateContent)...")
            
            t_tts_api_start = time.perf_counter()
            response_iterator = gemini_client.models.generate_content_stream(
                model=producer_model,
                contents=producer_tts_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=producer_voice_id,
                            )
                        )
                    ),
                )
            )

            # ... (rest of producer logic is unchanged)
            first_chunk_from_api = True 
            t_first_byte_received = None
            t_first_byte_queued = None

            for chunk_response in response_iterator:
                if t_first_byte_received is None:
                    t_first_byte_received = time.perf_counter()
                    print(f"    [Time] Gemini API First Byte Received (Producer): {t_first_byte_received - t_tts_api_start:.3f} seconds")

                if not chunk_response.candidates:
                    print("Warning: Empty candidate in Gemini TTS stream chunk. Skipping.")
                    if hasattr(chunk_response, 'prompt_feedback') and chunk_response.prompt_feedback:
                         safety_info = getattr(chunk_response.prompt_feedback, 'safety_ratings', "N/A")
                         block_reason = getattr(chunk_response.prompt_feedback, 'block_reason', "Unknown")
                         print(f"  (Feedback) Reason: {block_reason}, Safety Ratings: {safety_info}")
                    continue
                
                audio_content_bytes_chunk = None
                if chunk_response.candidates[0].content.parts:
                    for part in chunk_response.candidates[0].content.parts:
                        if hasattr(part, 'inline_data') and hasattr(part.inline_data, 'data'):
                            audio_content_bytes_chunk = part.inline_data.data
                            break 

                if audio_content_bytes_chunk:
                    temp_np_chunk = np.frombuffer(audio_content_bytes_chunk, dtype=GEMINI_TTS_DTYPE).copy()
                    
                    if first_chunk_from_api:
                        fade_duration_ms = 5
                        fade_samples = int(GEMINI_TTS_SAMPLERATE * (fade_duration_ms / 1000.0))
                        fade_samples = min(fade_samples, len(temp_np_chunk))

                        if fade_samples > 0:
                            fade_curve = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)**2
                            temp_np_chunk[:fade_samples] = (temp_np_chunk[:fade_samples].astype(np.float32) * fade_curve).astype(GEMINI_TTS_DTYPE)
                        
                        first_chunk_from_api = False 

                    audio_content_bytes_chunk_processed = temp_np_chunk.tobytes()
                    
                    producer_audio_queue.put(audio_content_bytes_chunk_processed)
                    if not producer_started_streaming_event.is_set():
                        producer_started_streaming_event.set()

                    if t_first_byte_queued is None:
                        t_first_byte_queued = time.perf_counter()
                        print(f"    [Time] Gemini API First Byte Queued (Producer): {t_first_byte_queued - t_tts_api_start:.3f} seconds")

                    if producer_save_enabled:
                        producer_all_audio_bytes_for_save.append(audio_content_bytes_chunk_processed)
                else:
                    print("Warning: Received empty audio data in a Gemini TTS stream chunk from API.")
            
            t_tts_api_end = time.perf_counter()
            api_duration = t_tts_api_end - t_tts_api_start
            print(f"    [Time] Gemini TTS API Call Duration (Producer): {api_duration:.3f} seconds")

        except Exception as e:
            print(f"Error in Gemini TTS producer thread: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            producer_audio_queue.put(None)
            print("Gemini TTS producer thread finished.")

    producer_thread = threading.Thread(
        target=_audio_producer_thread_func,
        args=(text, voice_id, instructions, gemini_tts_model, audio_queue, 
              all_audio_bytes_for_save, bool(output_filename), producer_started_streaming_event)
    )
    producer_thread.start()

    played_successfully = False
    playback_duration = 0.0

    if SOUND_LIBS_AVAILABLE:
        playback_finished_event = threading.Event()
        current_playback_buffer_bytes = b"" 
        
        # --- New Debugging Variable ---
        playback_underrun_count = 0

        def audio_playback_callback(outdata, frames, time_info, status):
            nonlocal current_playback_buffer_bytes
            nonlocal playback_underrun_count

            # --- New Debugging Logic ---
            # This block checks the status flag from sounddevice on every callback.
            # `output_underflow` is the specific flag for when the buffer runs empty.
            if status.output_underflow:
                playback_underrun_count += 1
                if DEBUG_AUDIO:
                    print(f"    [DEBUG] Audio Underrun #{playback_underrun_count} detected! (Pop/Glitch likely)")
            # --- End New Debugging Logic ---
            
            bytes_needed_for_frame = frames * GEMINI_TTS_CHANNELS * np.dtype(GEMINI_TTS_DTYPE).itemsize

            while len(current_playback_buffer_bytes) < bytes_needed_for_frame:
                try:
                    next_chunk_bytes = audio_queue.get(block=False) 
                    if next_chunk_bytes is None: 
                        break 
                    current_playback_buffer_bytes += next_chunk_bytes
                except queue.Empty:
                    if DEBUG_AUDIO:
                        # This log tells us the consumer had to wait for the producer.
                        qsize = audio_queue.qsize()
                        print(f"    [DEBUG] Queue empty while filling buffer (qsize={qsize}). Producer may be lagging.")
                    break 
                except Exception as cb_e_get:
                    print(f"    [Error in audio_callback queue get] {type(cb_e_get).__name__}: {cb_e_get}")
                    traceback.print_exc()
                    if not playback_finished_event.is_set(): playback_finished_event.set()
                    raise sd.CallbackStop 
            
            # ... (rest of callback logic is unchanged)
            current_audio_np = np.frombuffer(current_playback_buffer_bytes, dtype=GEMINI_TTS_DTYPE)
            samples_to_provide = min(len(current_audio_np), frames * GEMINI_TTS_CHANNELS)
            
            if samples_to_provide > 0:
                chunk_for_outdata = current_audio_np[:samples_to_provide]
                current_playback_buffer_bytes = current_playback_buffer_bytes[samples_to_provide * np.dtype(GEMINI_TTS_DTYPE).itemsize:]
                
                outdata_channels = outdata.shape[1]
                num_frames_to_fill = samples_to_provide // GEMINI_TTS_CHANNELS

                if GEMINI_TTS_CHANNELS == 1 and outdata_channels == 1: 
                    outdata[:num_frames_to_fill, 0] = chunk_for_outdata
                elif GEMINI_TTS_CHANNELS == 1 and outdata_channels > 1:
                    outdata[:num_frames_to_fill, :] = chunk_for_outdata.reshape(-1, 1) 
                else: 
                     outdata[:num_frames_to_fill, :min(outdata_channels, GEMINI_TTS_CHANNELS)] = chunk_for_outdata.reshape(num_frames_to_fill, min(outdata_channels, GEMINI_TTS_CHANNELS))
                     if outdata_channels > GEMINI_TTS_CHANNELS:
                        outdata[:num_frames_to_fill, GEMINI_TTS_CHANNELS:] = 0 

                if num_frames_to_fill < frames:
                    outdata[num_frames_to_fill:] = 0
            else: 
                outdata[:] = 0 
                if audio_queue.empty() and not producer_thread.is_alive(): 
                    if not playback_finished_event.is_set(): playback_finished_event.set()
                    raise sd.CallbackStop 
        
        t_playback_start_wall = time.perf_counter()

        try:
            device_info = sd.query_devices(kind='output')
            output_channels = device_info.get('max_output_channels', GEMINI_TTS_CHANNELS)
            if output_channels <= 0: output_channels = GEMINI_TTS_CHANNELS 
        except Exception as dev_e:
            print(f"    [Warning] Failed to query output device info: {dev_e}. Defaulting to source channels ({GEMINI_TTS_CHANNELS}).")
            output_channels = GEMINI_TTS_CHANNELS

        stream = sd.OutputStream(
            samplerate=GEMINI_TTS_SAMPLERATE,
            channels=output_channels,
            dtype=GEMINI_TTS_DTYPE,
            callback=audio_playback_callback
        )
        
        with stream:
            # ... (stream waiting logic is unchanged)
            producer_started_streaming_event.wait(timeout=10.0) 
            if not producer_started_streaming_event.is_set():
                print("    [Warning] Producer thread did not start streaming within timeout.")
                return False

            t_playback_actual_start = time.perf_counter()
            print(f"    [Time] Playback Stream Started (Consumer): {t_playback_actual_start - t_playback_start_wall:.3f} seconds (from stream setup start)")

            timeout_seconds = 600.0 
            playback_finished_event.wait(timeout=timeout_seconds)

        t_playback_end = time.perf_counter()
        
        # --- New Final Debugging Report ---
        if playback_underrun_count > 0:
            print(f"    [!] Playback Summary: {playback_underrun_count} audio underrun(s) detected. This is a likely source of 'pops'.")
        else:
            print(f"    [+] Playback Summary: 0 audio underruns detected. Playback was smooth.")
        # --- End New Final Debugging Report ---

        playback_duration = t_playback_end - t_playback_start_wall
        print(f"    [Time] Audio Playback Duration (Wall Time): {playback_duration:.3f} seconds")
        played_successfully = playback_finished_event.is_set()

    elif not SOUND_LIBS_AVAILABLE:
        # ... (unchanged)
        print("Audio playback skipped (sounddevice/soundfile not available).")
        producer_thread.join()
        played_successfully = True 

    # ... (rest of file is unchanged)
    saved_successfully = False
    if output_filename:
        producer_thread.join() 
        if all_audio_bytes_for_save:
            try:
                full_audio_data_bytes = b"".join(all_audio_bytes_for_save)
                full_audio_data_np = np.frombuffer(full_audio_data_bytes, dtype=GEMINI_TTS_DTYPE)
                if not output_filename.lower().endswith(('.wav')):
                    output_filename = output_filename + ".wav" 
                    print(f"Adjusted output filename to: {output_filename} (Gemini TTS outputs WAV)")
                output_dir = os.path.dirname(output_filename)
                if output_dir and not os.path.exists(output_dir):
                     os.makedirs(output_dir, exist_ok=True)
                     print(f"Created output directory: {output_dir}")
                sf.write(output_filename, full_audio_data_np, GEMINI_TTS_SAMPLERATE)
                print(f"Audio saved to: {output_filename}")
                saved_successfully = True
            except Exception as e:
                print(f"Error saving Gemini TTS audio file '{output_filename}': {e}")
                traceback.print_exc()
        else:
             print("Skipping save: No audio data received from API (or producer thread failed).")
             saved_successfully = False
    else:
         saved_successfully = played_successfully 

    return bool(all_audio_bytes_for_save) and (saved_successfully or (played_successfully and not output_filename))

def get_voices() -> Dict[str, List[Dict[str, str]]]:
    # ... (this function is unchanged)
    print("Fetching available voices from Gemini TTS (hardcoded list)...")
    voices_data = [
        {"id": "Zephyr", "name": "Zephyr", "gender": "female"}, {"id": "Puck", "name": "Puck", "gender": "male"}, {"id": "Charon", "name": "Charon", "gender": "male"}, {"id": "Kore", "name": "Kore", "gender": "female"}, {"id": "Fenrir", "name": "Fenrir", "gender": "male"}, {"id": "Leda", "name": "Leda", "gender": "female"}, {"id": "Orus", "name": "Orus", "gender": "male"}, {"id": "Aoede", "name": "Aoede", "gender": "female"}, {"id": "Callirrhoe", "name": "Callirrhoe", "gender": "female"}, {"id": "Autonoe", "name": "Autonoe", "gender": "female"}, {"id": "Enceladus", "name": "Enceladus", "gender": "male"}, {"id": "Iapetus", "name": "Iapetus", "gender": "male"}, {"id": "Umbriel", "name": "Umbriel", "gender": "male"}, {"id": "Algieba", "name": "Algieba", "gender": "male"}, {"id": "Despina", "name": "Despina", "gender": "female"}, {"id": "Erinome", "name": "Erinome", "gender": "female"}, {"id": "Algenib", "name": "Algenib", "gender": "male"}, {"id": "Rasalgethi", "name": "Rasalgethi", "gender": "male"}, {"id": "Laomedeia", "name": "Laomedeia", "gender": "female"}, {"id": "Achernar", "name": "Achernar", "gender": "male"}, {"id": "Alnilam", "name": "Alnilam", "gender": "male"}, {"id": "Schedar", "name": "Schedar", "gender": "male"}, {"id": "Gacrux", "name": "Gacrux", "gender": "male"}, {"id": "Pulcherrima", "name": "Pulcherrima", "gender": "female"}, {"id": "Achird", "name": "Achird", "gender": "male"}, {"id": "Zubenelgenubi", "name": "Zubenelgenubi", "gender": "male"}, {"id": "Vindemiatrix", "name": "Vindemiatrix", "gender": "female"}, {"id": "Sadachbia", "name": "Sadachbia", "gender": "male"}, {"id": "Sadaltager", "name": "Sadaltager", "gender": "male"}, {"id": "Sulafat", "name": "Sulafat", "gender": "female"}, ]
    male_voices = []
    female_voices = []
    for voice in voices_data:
        voice_entry = {"id": voice["id"], "name": voice["name"]}
        if voice["gender"] == "male": male_voices.append(voice_entry)
        elif voice["gender"] == "female": female_voices.append(voice_entry)
    print(f"Found {len(male_voices)} perceived male voices and {len(female_voices)} perceived female voices for Gemini TTS.")
    return {"male": male_voices, "female": female_voices}

if __name__ == '__main__':
    # ... (this section is unchanged)
    print("\n--- Gemini TTS Module Test (True Streaming Enabled) ---")
    import dotenv
    dotenv.load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"): print("Cannot run test: GOOGLE_API_KEY not set in .env"); exit(1)
    class MockConfig:
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "models/tts-1")
    config = MockConfig()
    available_voices = get_voices()
    print("\nAvailable Voices:"); print("Male:", available_voices.get('male', [])); print("Female:", available_voices.get('female', []))
    if available_voices['female']:
        test_voice_id = "Kore"
        test_text = "This is a test to see if we can detect audio buffer underruns, which are often heard as pops or glitches in the audio stream."
        test_instructions = "Speak clearly and at a normal pace."
        print(f"\nTesting true streaming synthesis and playback with voice: {test_voice_id}")
        if SOUND_LIBS_AVAILABLE:
            success = synthesize(test_text, test_voice_id, instructions=test_instructions)
            print(f"Playback Test Result: {'Success' if success else 'Failed'}")
        else: print("Skipping playback test (sound libraries not available).")