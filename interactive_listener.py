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
def run_analysis_pipeline(image_path: str, voice_selector_instance: voice_selector.VoiceSelector):
    """
    Runs the analysis and synthesis pipeline for a given image path.
    Uses the globally imported synthesize_speech function.
    """
    global is_processing
    print("-" * 30)

    character_info = image_analyzer.get_info_from_screenshot(image_path)

    if character_info:
        char_name = character_info.get("character_name", "Unknown")
        gender = character_info.get("gender", "Unknown")
        dialogue = character_info.get("dialogue", "")

        print("\n--- Extracted Information ---")
        print(f"Character Name: {char_name}")
        print(f"Gender: {gender}")
        print(f"Dialogue: '{dialogue}'")
        print("---------------------------\n")

        # Get Voice ID (Local Logic)
        selected_voice_id = voice_selector_instance.find_or_assign_voice(char_name, gender)

        # Speak Dialogue
        if dialogue:
            if selected_voice_id:
                print(f"Attempting to speak dialogue using voice ID: {selected_voice_id}")
                success = synthesize_speech(
                    text=dialogue,
                    voice_id=selected_voice_id,
                    output_filename=None # Don't save file in interactive mode by default
                )
                if not success:
                    print("Failed to synthesize or play audio.")
            else:
                print("Error: Could not determine a voice ID (including fallback). Cannot speak dialogue.")
        else:
            print("No dialogue found in the screenshot to speak.")

        # Save Mapping if Updated
        voice_selector_instance.save_map()

    else:
        print("Failed to get character information from the screenshot.")

    print("-" * 30)
    print(f"\nReady. Press '{config.TRIGGER_KEY}' to capture and process, 'ESC' to exit.")
    is_processing = False # Reset processing flag


# --- Screenshot and Trigger Function ---
def capture_and_process(vs_instance: voice_selector.VoiceSelector):
    """
    Captures a screenshot, saves it temporarily, and triggers the pipeline.
    """
    global is_processing
    if is_processing:
        print("Already processing a screenshot. Please wait.")
        return

    is_processing = True
    print(f"\n'{config.TRIGGER_KEY}' detected! Capturing screenshot...")

    temp_file = None
    try:
        # Capture the primary screen
        screenshot = ImageGrab.grab()

        # Create a temporary file to save the screenshot
        # Use a recognizable suffix and keep the file until explicitly deleted
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        screenshot.save(temp_file.name, "PNG")
        print(f"Screenshot saved temporarily to: {temp_file.name}")

        # Run the analysis pipeline using the temp file path
        run_analysis_pipeline(temp_file.name, vs_instance)

    except FileNotFoundError:
        print("Error: Failed to create temporary file.")
        is_processing = False
    except OSError as e:
         print(f"Error capturing or saving screenshot: {e}")
         print("Ensure necessary permissions or try running as administrator/sudo.")
         is_processing = False
    except Exception as e:
        print(f"An unexpected error occurred during capture/process: {e}")
        is_processing = False # Reset flag on error
    finally:
        # Clean up the temporary file
        if temp_file:
            try:
                temp_file.close() # Close the file handle
                os.unlink(temp_file.name) # Delete the file
                # print(f"Temporary file {temp_file.name} deleted.")
            except Exception as e:
                print(f"Warning: Failed to delete temporary file {temp_file.name}: {e}")
                # is_processing should already be False unless error happened before finally
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