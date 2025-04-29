import argparse
import os
import sys

# Add project root to path to allow importing config, data_manager etc.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import config
import data_manager

# --- Dynamic TTS Module Import ---
try:
    if config.TTS_PROVIDER == 'elevenlabs':
        from tts_elevenlabs import get_voices
        print("Fetching voices using ElevenLabs backend.")
    elif config.TTS_PROVIDER == 'google':
        from tts_google import get_voices
        print("Fetching voices using Google TTS backend.")
    elif config.TTS_PROVIDER == 'openai':
        from tts_openai import get_voices
        print("Fetching hardcoded voices...sadly. Openai doesn't do basic APIs eh?") 
    else:
        raise ImportError(f"TTS Provider '{config.TTS_PROVIDER}' is not supported by fetch script.")
except ImportError as e:
    print(f"Error importing TTS module for provider '{config.TTS_PROVIDER}': {e}")
    print("Please ensure the corresponding TTS module (e.g., tts_elevenlabs.py) exists and required libraries are installed.")
    exit(1)
except Exception as e:
    print(f"An unexpected error occurred during TTS module import: {e}")
    exit(1)


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Fetch voices from the configured TTS provider ({config.TTS_PROVIDER}) and save to {config.VOICES_PATH}."
        )
    parser.add_argument(
        "-o", "--output",
        default=config.VOICES_PATH, # Default to path defined in config
        help=f"Path to the output JSON file (default: {config.VOICES_PATH})."
        )
    # Add optional arguments for sorting or limiting if desired (implement logic below)
    # parser.add_argument("-n", "--num_voices", type=int, help="Limit to top N voices per gender (if supported/implemented)")
    args = parser.parse_args()

    print(f"Fetching voices for TTS provider: {config.TTS_PROVIDER}")

    # Call the dynamically imported get_voices function
    available_voices = get_voices() # This should return the standardized dict

    # --- Post-processing (Optional: Sorting/Limiting) ---
    # Example: If voices have 'likes' or other sortable metrics (more common for ElevenLabs)
    # if config.TTS_PROVIDER == 'elevenlabs' and 'likes' in available_voices.get('male', [{}])[0]:
    #     print("Sorting voices by likes (descending)...")
    #     available_voices['male'].sort(key=lambda x: x.get('likes', 0), reverse=True)
    #     available_voices['female'].sort(key=lambda x: x.get('likes', 0), reverse=True)
    #     if args.num_voices:
    #           print(f"Limiting to top {args.num_voices} voices per gender...")
    #           available_voices['male'] = available_voices['male'][:args.num_voices]
    #           available_voices['female'] = available_voices['female'][:args.num_voices]

    # --- Save the Fetched Voices ---
    output_path = args.output
    if available_voices and (available_voices.get('male') or available_voices.get('female')):
        print(f"\nSaving fetched voice data to: {output_path}")
        data_manager.save_json_data(available_voices, output_path)
        print("Voice data saved successfully.")
    else:
        print("\nNo voice data was fetched or the result was empty. Skipping save.")
        # Optionally save an empty structure if needed for consistency
        # print(f"Saving empty voice structure to: {output_path}")
        # data_manager.save_json_data({'male': [], 'female': []}, output_path)

    print("\nVoice fetching process complete.")