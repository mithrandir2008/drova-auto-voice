import os
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv
import argparse

def get_premade_english_voices(client: ElevenLabs) -> dict:
    """
    Fetches voices using get_all() (likely premade/cloned),
    filters for English and by gender.

    Note: This method likely retrieves premade voices which may not have
          'liked_by_count' populated. Sorting by popularity is not effective here.

    Args:
        client: An initialized ElevenLabs client instance.

    Returns:
        A dictionary: {'male': [(name, id), ...], 'female': [(name, id), ...]}
        Returns empty lists if an error occurs or no voices are found.
    """
    print("Fetching voices using get_all() (likely includes premade voices)...")
    male_voices = []
    female_voices = []
    other_voices = []

    try:
        all_voices_response = client.voices.get_all()

        if not all_voices_response or not hasattr(all_voices_response, 'voices'):
            print("Warning: Could not retrieve voices or response format unexpected.")
            return {'male': [], 'female': [], 'other' : []}

        all_voices = all_voices_response.voices
        print(f"Found {len(all_voices)} total voices from get_all(). Filtering for English Male/Female...")

        # --- Filtering and Data Collection ---
        for voice in all_voices:
            # --- Debug Print (Optional: Uncomment to inspect) ---
            # print("-" * 10)
            # try:
            #     print(f"Inspecting Voice: Name={getattr(voice, 'name', 'N/A')}, ID={getattr(voice, 'voice_id', 'N/A')}")
            #     # Use vars() to see all attributes the library populated
            #     print(vars(voice))
            #     if hasattr(voice, 'sharing') and voice.sharing:
            #          print(f"Sharing Info: {vars(voice.sharing)}")
            # except Exception as e:
            #     print(f"Error inspecting voice: {e}")
            # print("-" * 10)
            # --- End Debug Print ---


            # Default values
            gender = "unknown"
            is_english = False
            # Availability check might be less critical for premade, but good practice
            is_available = True # Assume available unless proven otherwise
            name = getattr(voice, 'name', 'Unnamed Voice')
            voice_id = getattr(voice, 'voice_id', None)
            category = getattr(voice, 'category', 'unknown') # Check if it's 'premade'

            if not voice_id:
                continue # Skip if no voice ID

            # 1. Check Gender (using labels)
            if voice.labels and isinstance(voice.labels, dict):
                gender = voice.labels.get("gender", "unknown").lower()

            # 2. Check Language (prefer verified_languages, fallback to accent label)
            if voice.verified_languages and isinstance(voice.verified_languages, list):
                 for lang_info in voice.verified_languages:
                      if hasattr(lang_info, 'language') and lang_info.language == 'en':
                           is_english = True
                           break
            elif not is_english and voice.labels and isinstance(voice.labels, dict):
                 accent = voice.labels.get("accent", "").lower()
                 if accent in ["american", "british", "australian", "english", "uk", "us"]:
                      is_english = True

            # 3. Check Availability (optional refinement)
            # If using sharing status:
            # if hasattr(voice, 'sharing') and voice.sharing is not None:
            #      is_available = getattr(voice.sharing, 'enabled_in_library', True) # Example check

            # --- Apply Filters ---
            # Filter only for premade voices if desired (optional)
            # if is_english and is_available and category == 'premade':
            if is_english and is_available: # Keep it simple for now
                 voice_data = {"name": name, "id": voice_id, "category": category}
                 if gender == "male":
                     male_voices.append(voice_data)
                 elif gender == "female":
                     female_voices.append(voice_data)
                 else:
                    other_voices.append(voice_data)

        print(f"Filtered down to {len(male_voices)} English male voices and {len(female_voices)} English female voices. Other voices {len(other_voices)}")

        # Sort alphabetically by name for consistent listing
        male_voices.sort(key=lambda x: x["name"])
        female_voices.sort(key=lambda x: x["name"])
        other_voices.sort(key=lambda x: x["name"])

        # Return just name and id tuples
        final_male = [(v["name"], v["id"]) for v in male_voices]
        final_female = [(v["name"], v["id"]) for v in female_voices]
        final_other = [(v["name"], v["id"]) for v in other_voices]

        return {"male": final_male, "female": final_female, "other": final_other}

    except Exception as e:
        print(f"Error fetching or processing ElevenLabs voices: {e}")
        return {'male': [], 'female': []}

# --- Main Execution ---
if __name__ == "__main__":
    load_dotenv()
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    if not ELEVENLABS_API_KEY:
        print("Error: ELEVENLABS_API_KEY not found in .env file or environment variables.")
        exit(1)

    parser = argparse.ArgumentParser(description="Fetch and display English premade/cloned voices from ElevenLabs using get_all().")
    # Removed --num_voices as we list all found matching ones now
    # parser.add_argument("-n", "--num_voices", type=int, default=15, help="Approximate number of voices per gender (actual count may vary).")
    args = parser.parse_args()

    try:
        print("Initializing ElevenLabs client...")
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("Client initialized.")
    except Exception as e:
        print(f"Error: Failed to initialize ElevenLabs client: {e}")
        exit(1)

    # Fetch the voices using the revised function
    available_voices = get_premade_english_voices(client) # Pass client instance

    # Display the results (without likes, sorted alphabetically)
    print("\n--- English Male Voices (from get_all, sorted alphabetically) ---")
    if available_voices['male']:
        for i, (name, voice_id) in enumerate(available_voices['male']):
            # Limit the list length if needed using args.num_voices if you re-add it
            # if i >= args.num_voices: break
            print(f"{i+1:2d}. Name: {name:<20} ID: {voice_id:<25}")
    else:
        print("No male voices found matching criteria.")

    print("\n--- English Female Voices (from get_all, sorted alphabetically) ---")
    if available_voices['female']:
        for i, (name, voice_id) in enumerate(available_voices['female']):
            # Limit the list length if needed using args.num_voices if you re-add it
            # if i >= args.num_voices: break
            print(f"{i+1:2d}. Name: {name:<20} ID: {voice_id:<25}")
    else:
        print("No female voices found matching criteria.")
    
    if available_voices['other']:
        for i, (name, voice_id) in enumerate(available_voices['other']):
            # Limit the list length if needed using args.num_voices if you re-add it
            # if i >= args.num_voices: break
            print(f"{i+1:2d}. Name: {name:<20} ID: {voice_id:<25}")
    else:
        print("No other voices found matching criteria.")

    print("\nVoice fetching complete. Note: Like counts are generally not available for voices listed via get_all().")
    print("Check the ElevenLabs Voice Library website for public voices and popularity.")