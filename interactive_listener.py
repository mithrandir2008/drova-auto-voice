import time
import os
import tempfile
import keyboard # For listening to key presses
from PIL import ImageGrab # For taking screenshots
import argparse # Keep argparse for potential future flags

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

    # --- 1. Gemini Analysis ---
    t_start_gemini = time.perf_counter()
    character_info = image_analyzer.get_info_from_screenshot(image_path)
    t_end_gemini = time.perf_counter()
    gemini_duration = t_end_gemini - t_start_gemini
    print(f"  [Time] Gemini Analysis (Total): {gemini_duration:.3f} seconds")

    synthesis_triggered = False
    tts_duration = 0.0
    select_duration = 0.0

    if character_info:
        char_name = character_info.get("character_name", "Unknown")
        gender = character_info.get("gender", "Unknown")
        dialogue = character_info.get("dialogue", "")

        print("\n--- Extracted Information ---")
        print(f"Character Name: {char_name}")
        print(f"Gender: {gender}")
        print(f"Dialogue: '{dialogue}'")
        print("---------------------------\n")

        # --- 2. Voice Selection ---
        t_start_select = time.perf_counter()
        selected_voice_id = voice_selector_instance.find_or_assign_voice(char_name, gender)
        t_end_select = time.perf_counter()
        select_duration = t_end_select - t_start_select
        print(f"  [Time] Voice Selection: {select_duration:.4f} seconds") # Higher precision for fast ops

        # --- 3. TTS Synthesis + Playback ---
        if dialogue:
            if selected_voice_id:
                synthesis_triggered = True
                print(f"[Pipeline] Starting TTS Synthesis + Playback (Voice ID: {selected_voice_id})...")
                t_start_tts = time.perf_counter()
                success = synthesize_speech(
                    text=dialogue,
                    voice_id=selected_voice_id,
                    output_filename=None # Don't save file in interactive mode
                )
                t_end_tts = time.perf_counter()
                tts_duration = t_end_tts - t_start_tts
                print(f"  [Time] TTS Synthesis + Playback (Total): {tts_duration:.3f} seconds")
                if not success:
                    print("[Pipeline] Failed to synthesize or play audio.")
            else:
                print("[Pipeline] Error: Could not determine a voice ID. Cannot speak dialogue.")
        else:
            print("[Pipeline] No dialogue found to speak.")

        # Save Mapping if Updated
        voice_selector_instance.save_map()

    else:
        print("Failed to get character information from the screenshot.")

    pipeline_end_time = time.perf_counter()
    total_pipeline_duration = pipeline_end_time - pipeline_start_time
    total_roundtrip = pipeline_end_time - trigger_time # Time since key press

    print("-" * 30)
    print("[Timing Summary]")
    print(f"  - Gemini Analysis:       {gemini_duration:.3f} s")
    if character_info: # Only print these if analysis succeeded
      print(f"  - Voice Selection:       {select_duration:.4f} s")
      if synthesis_triggered:
          print(f"  - TTS + Playback:      {tts_duration:.3f} s")
      else:
          print(f"  - TTS + Playback:      N/A")
    print(f"  - Pipeline Execution:    {total_pipeline_duration:.3f} s")
    print(f"  - Total Roundtrip Time:  {total_roundtrip:.3f} s")
    print("-" * 30)


    print(f"\nReady. Press '{config.TRIGGER_KEY}' to capture and process, 'ESC' to exit.")
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
    args = parser.parse_args()

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