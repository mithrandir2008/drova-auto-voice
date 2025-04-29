import argparse
import os

# Local Imports
import config
import image_analyzer
import voice_selector
import data_manager # Although used by voice_selector, keep import for clarity if needed
import utils

# --- Dynamic TTS Module Import ---
try:
    if config.TTS_PROVIDER == 'elevenlabs':
        from tts_elevenlabs import synthesize as synthesize_speech
        print("Using ElevenLabs TTS backend.")
    elif config.TTS_PROVIDER == 'google':
        from tts_google import synthesize as synthesize_speech
        print("Using Google TTS backend.")
    elif config.TTS_PROVIDER == 'openai':
        from tts_openai import synthesize as synthesize_speech
        print("Using Openai TTS backend.")
    else:
        # This case is redundant due to config check, but good practice
        raise ImportError(f"TTS Provider '{config.TTS_PROVIDER}' is not supported.")
except ImportError as e:
    print(f"Error importing TTS module for provider '{config.TTS_PROVIDER}': {e}")
    print("Please ensure the corresponding TTS module (e.g., tts_elevenlabs.py) exists and required libraries are installed.")
    exit(1)
except Exception as e:
    print(f"An unexpected error occurred during TTS module import: {e}")
    exit(1)

# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process screenshot, map character to voice, speak dialogue.")
    parser.add_argument("image_path", help="Path to the screenshot image file.")
    parser.add_argument(
        "-o", "--output",
        help="Optional: Save the generated audio to this file path (e.g., output.mp3). Directory will be created if needed.",
        default=None
        )
    # Removed --voice_list and --mapping_file args, now handled by config.py
    args = parser.parse_args()

    # Validate image path early
    if not os.path.exists(args.image_path) or not os.path.isfile(args.image_path):
        print(f"Error: Image file not found or is not a file: {args.image_path}")
        exit(1)

    # --- Initialize Voice Selector ---
    # Uses paths from config
    vs = voice_selector.VoiceSelector(config.VOICES_PATH, config.MAPPING_PATH)
    vs.load_data() # Load voices.json and character_voices.json

    # --- Process Screenshot ---
    character_info = image_analyzer.get_info_from_screenshot(args.image_path)

    if character_info:
        char_name = character_info.get("character_name", "Unknown")
        gender = character_info.get("gender", "Unknown") # Already standardized by image_analyzer
        dialogue = character_info.get("dialogue", "")   # Already standardized by image_analyzer

        print("\n--- Extracted Information ---")
        print(f"Character Name: {char_name}")
        print(f"Gender: {gender}")
        print(f"Dialogue: '{dialogue}'")
        print("---------------------------\n")

        # --- Get Voice ID (Local Logic) ---
        selected_voice_id = vs.find_or_assign_voice(char_name, gender)

        # --- Speak Dialogue ---
        if dialogue:
            if selected_voice_id:
                print(f"Attempting to speak dialogue using voice ID: {selected_voice_id}")
                success = synthesize_speech(
                    text=dialogue,
                    voice_id=selected_voice_id, # Use the ID returned by voice_selector
                    output_filename=args.output # Pass the output path
                )
                if not success:
                    print("Failed to synthesize or play/save audio.")
            else:
                print("Error: Could not determine a voice ID (including fallback). Cannot speak dialogue.")
        else:
            print("No dialogue found in the screenshot to speak.")

        # --- Save Mapping if Updated ---
        vs.save_map() # Saves the map if find_or_assign_voice updated it

    else:
        print("Failed to get character information from the screenshot.")

    print("\nScript finished.")