import time
import os
import tempfile
import keyboard # For listening to key presses
from PIL import ImageGrab # For taking screenshots
import argparse # Keep argparse for potential future flags
import traceback

# --- Standard Project Imports ---
import config
import image_analyzer
import voice_selector
import data_manager # Although used by voice_selector, keep import for clarity if needed
import utils

# --- Dynamic TTS Module Import (Copied from main_orchestrator) ---
try:
    if config.TTS_PROVIDER == 'elevenlabs':
        from tts_elevenlabs import synthesize as synthesize_speech
        print(f"Using ElevenLabs TTS backend ({config.ELEVENLABS_MODEL_ID}).")
    elif config.TTS_PROVIDER == 'google':
        from tts_google import synthesize as synthesize_speech
        print("Using Google TTS backend.")
    elif config.TTS_PROVIDER == 'openai':
        from tts_openai import synthesize as synthesize_speech
        print("Using Openai TTS backend.")
    elif config.TTS_PROVIDER == 'gemini_tts':
        from tts_gemini import synthesize as synthesize_speech
        print("Using Openai TTS backend.")
    else:
        raise ImportError(f"TTS Provider '{config.TTS_PROVIDER}' is not supported.")
except ImportError as e:
    print(f"Error importing TTS module for provider '{config.TTS_PROVIDER}': {e}")
    print("Please ensure the corresponding TTS module exists and required libraries are installed.")
    exit(1)
except Exception as e:
    print(f"An unexpected error occurred during TTS module import: {e}")
    exit(1)

# --- Global flags ---
# Flag to signal the main loop to exit
request_exit = False
# Flag to prevent processing multiple screenshots simultaneously if key held down
is_processing = False

# --- Core Processing Function ---
def run_analysis_pipeline(image_path: str, voice_selector_instance: voice_selector.VoiceSelector, trigger_time: float): # Add trigger_time
    """
    Runs the analysis and synthesis pipeline for a given image path.
    Uses the globally imported synthesize_speech function.
    Prints timing information for each major step.
    """
    global is_processing
    pipeline_start_time = time.perf_counter() # Start timing the pipeline itself

    print("-" * 30)

    # --- 1. Gemini Analysis (includes Persona Generation) ---
    t_start_gemini = time.perf_counter()
    # This now returns name, gender, dialogue, AND persona_instructions
    character_info = image_analyzer.get_info_from_screenshot(image_path)
    t_end_gemini = time.perf_counter()
    gemini_duration = t_end_gemini - t_start_gemini
    print(f"  [Time] Gemini Analysis + Persona Gen: {gemini_duration:.3f} seconds")

    synthesis_triggered = False
    tts_duration = 0.0
    select_duration = 0.0
    selected_voice_id = None
    stored_persona = ""

    if character_info:
        char_name = character_info.get("character_name", "Unknown")
        gender = character_info.get("gender", "Unknown")
        dialogue = character_info.get("dialogue", "")
        # Get the persona generated by Gemini in this run
        generated_persona = character_info.get("persona_instructions", "")

        print("\n--- Extracted Information ---")
        print(f"Character Name: {char_name}")
        print(f"Gender: {gender}")
        print(f"Dialogue: '{dialogue}'")
        print("---------------------------\n")
        if generated_persona:
             # Only show a snippet of the potentially long persona
             persona_snippet = (generated_persona[:70] + '...') if len(generated_persona) > 70 else generated_persona
             print(f"Generated Persona: '{persona_snippet}'")
        print("---------------------------\n")

        # --- 2. Voice Selection ---
        t_start_select = time.perf_counter()
        # Pass the newly generated persona to be stored *if* the character is new.
        # This function now returns BOTH the voice_id and the stored/new persona.
        selected_voice_id, stored_persona = voice_selector_instance.find_or_assign_voice(
            char_name,
            gender,
            generated_persona # Provide the freshly generated persona
        )
        t_end_select = time.perf_counter()
        select_duration = t_end_select - t_start_select
        print(f"  [Time] Voice Selection & Persona Store/Retrieve: {select_duration:.4f} seconds")


        # --- 3. TTS Synthesis + Playback ---
        if dialogue:
            if selected_voice_id:
                synthesis_triggered = True
                print(f"[Pipeline] Starting TTS Synthesis + Playback (Voice ID: {selected_voice_id})...")

                # Prepare keyword arguments for synthesize_speech
                synthesis_kwargs = {
                    "text": dialogue,
                    "voice_id": selected_voice_id,
                    "output_filename": None
                }

                # Add 'instructions' ONLY if using OpenAI AND a persona exists for this char
                if config.TTS_PROVIDER == 'openai' and stored_persona:
                    synthesis_kwargs["instructions"] = stored_persona
                    print(f"  -> Providing stored OpenAI TTS persona instructions.")
                elif config.TTS_PROVIDER == 'openai' and not stored_persona:
                     print(f"  -> No stored persona found for '{char_name}'. Synthesizing with default delivery.")


                t_start_tts = time.perf_counter()
                try:
                    success = synthesize_speech(**synthesis_kwargs)
                except TypeError as te:
                     if 'instructions' in str(te) and config.TTS_PROVIDER == 'openai':
                          print(f"  [Error] Your tts_openai.py's synthesize function needs to accept the 'instructions' argument.")
                          print("          Please update tts_openai.py. Attempting synthesis without instructions...")
                          synthesis_kwargs.pop('instructions', None)
                          success = synthesize_speech(**synthesis_kwargs)
                     elif 'instructions' in str(te):
                          # Provider isn't OpenAI, but somehow instructions were passed? Ignore.
                           synthesis_kwargs.pop('instructions', None)
                           success = synthesize_speech(**synthesis_kwargs)
                     else:
                          raise # Re-raise other TypeErrors
                except Exception as synth_e:
                     print(f"  [Error] An unexpected error occurred during synthesis: {synth_e}")
                     traceback.print_exc()
                     success = False

                t_end_tts = time.perf_counter()
                tts_duration = t_end_tts - t_start_tts
                print(f"  [Time] TTS Synthesis + Playback (Total): {tts_duration:.3f} seconds")
                if not success:
                    print("[Pipeline] Failed to synthesize or play audio.")
            else:
                print("[Pipeline] Error: Could not determine a voice ID. Cannot speak dialogue.")
        else:
            print("[Pipeline] No dialogue found to speak.")

        # Save Mapping if Updated (VoiceSelector handles the flag)
        voice_selector_instance.save_map()

    else:
        print("Failed to get character information from the screenshot.")

    pipeline_end_time = time.perf_counter()
    total_pipeline_duration = pipeline_end_time - pipeline_start_time
    total_roundtrip = pipeline_end_time - trigger_time

    print("-" * 30)
    print("[Timing Summary]")
    print(f"  - Gemini Analysis+Persona: {gemini_duration:.3f} s")
    if character_info:
      print(f"  - Voice Select/Persona:  {select_duration:.4f} s")
      if synthesis_triggered:
          print(f"  - TTS + Playback:      {tts_duration:.3f} s")
      else:
          print(f"  - TTS + Playback:      N/A")
    print(f"  - Pipeline Execution:    {total_pipeline_duration:.3f} s")
    print(f"  - Total Roundtrip Time:  {total_roundtrip:.3f} s")
    print("-" * 30)

    print(f"\nReady. Press '{config.TRIGGER_KEY}' to capture and process, '{config.EXIT_KEY}' to exit.")
    is_processing = False # Reset processing flag


# --- Screenshot and Trigger Function ---
def capture_and_process(vs_instance: voice_selector.VoiceSelector):
    """
    Captures a screenshot, saves it temporarily, and triggers the pipeline.
    """
    global is_processing
    trigger_time = time.perf_counter() # Record time immediately on trigger

    if is_processing:
        print("Already processing a screenshot. Please wait.")
        return

    is_processing = True
    print(f"\n'{config.TRIGGER_KEY}' detected! Capturing screenshot...")

    temp_file = None
    capture_duration = 0.0
    try:
        # --- 0. Screenshot Capture/Save ---
        t_start_capture = time.perf_counter()
        screenshot = ImageGrab.grab()
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        screenshot.save(temp_file.name, "PNG")
        t_end_capture = time.perf_counter()
        capture_duration = t_end_capture - t_start_capture
        print(f"Screenshot saved temporarily to: {temp_file.name}")
        print(f"  [Time] Screenshot Capture/Save: {capture_duration:.3f} seconds")

        # Run the analysis pipeline using the temp file path, pass trigger time
        run_analysis_pipeline(temp_file.name, vs_instance, trigger_time)

    # ... (rest of exception handling) ...
    except Exception as e:
        print(f"An unexpected error occurred during capture/process: {e}")
        is_processing = False # Reset flag on error
    finally:
        # --- Cleanup ---
        t_start_cleanup = time.perf_counter()
        if temp_file:
            try:
                temp_file.close()
                os.unlink(temp_file.name)
            except Exception as e:
                print(f"Warning: Failed to delete temporary file {temp_file.name}: {e}")
        t_end_cleanup = time.perf_counter()
        # print(f"  [Time] Temp File Cleanup: {t_end_cleanup - t_start_cleanup:.4f} seconds") # Optional

        # Ensure processing flag is reset if not already done by run_analysis_pipeline
        if is_processing: is_processing = False


# --- Exit Function ---
def signal_exit():
    """Sets the flag to terminate the main loop."""
    global request_exit
    if not request_exit: # Prevent multiple exit messages if key held
        print("\nExit key (ESC) detected. Shutting down...")
        request_exit = True

# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Listens for a hotkey to capture screen, analyze, and speak dialogue.")
    # Add arguments if needed in the future, e.g., --trigger-key
    # parser.add_argument("--trigger-key", default="`", help="Hotkey to trigger screenshot capture.")
    # ADDED: Argument to clear cache
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the cached voice list and character mappings for the currently configured TTS provider before running."
    )
    args = parser.parse_args()

    # ADDED: Logic to handle cache clearing
    if args.clear_cache:
        print(f"--- Clearing cache for provider: {config.TTS_PROVIDER} ---")
        files_to_clear = [config.VOICES_PATH, config.MAPPING_PATH]
        for f_path in files_to_clear:
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    print(f"Successfully deleted: {f_path}")
                except OSError as e:
                    print(f"Error deleting file {f_path}: {e}")
            else:
                print(f"Cache file not found (already clean): {f_path}")
        print("--- Cache cleared. Proceeding with execution. ---\n")

    # --- Configuration for Hotkeys ---
    # TODO: Move these to config.py if preferred
    config.TRIGGER_KEY = "`" # Tilde key (often above Tab)
    config.EXIT_KEY = "esc" # Escape key

    print("--- Interactive Screenshot Listener ---")
    print(f" TTS Provider: {config.TTS_PROVIDER}")
    print(f" Gemini Model: {config.GEMINI_MODEL}")
    print("-" * 35)
    print("Initializing...")

    # --- Initialize Voice Selector ---
    vs = voice_selector.VoiceSelector(config.VOICES_PATH, config.MAPPING_PATH)
    vs.load_data()

    # --- Setup Hotkeys ---
    # Note: This might require admin/sudo rights, especially on Linux.
    try:
        # Pass the voice selector instance to the callback
        keyboard.add_hotkey(config.TRIGGER_KEY, lambda: capture_and_process(vs))
        keyboard.add_hotkey(config.EXIT_KEY, signal_exit)

        print(f"\nReady. Press '{config.TRIGGER_KEY}' to capture and process screen.")
        print(f"Press '{config.EXIT_KEY}' to exit.")

        # --- Main Loop ---
        while not request_exit:
            # Keep the script alive while waiting for hotkeys
            # time.sleep(0.1) is a simple way to pause without high CPU usage
            # keyboard.wait() could also be used but makes checking the flag harder
            time.sleep(0.1)

    except ImportError:
         print("\nERROR: 'keyboard' library not found. Please install it: pip install keyboard")
         print("Note: On Linux, 'keyboard' usually requires running as root (sudo).")
         print("On Windows, administrator privileges might be needed.")
         exit(1)
    except Exception as e:
         print(f"\nAn error occurred setting up hotkeys: {e}")
         print("This might be due to permissions issues (try running as admin/sudo)")
         print("or the keyboard library might not be compatible with your system/environment.")
         exit(1)
    finally:
        # --- Cleanup ---
        print("Cleaning up hotkeys...")
        try:
            keyboard.unhook_all()
        except Exception as e:
            print(f"Warning: Error unhooking keyboard listeners: {e}")
        print("Script finished.")