import os
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv
import argparse
import json # Import the json library

def get_elevenlabs_voices(client: ElevenLabs, num_male: int = 15, num_female: int = 15) -> dict:
    """
    Fetches available English voices from ElevenLabs, filters by gender,
    sorts by popularity (likes), and returns the top N for each.

    Args:
        client: An initialized ElevenLabs client instance.
        num_male: The maximum number of top male voices to return.
        num_female: The maximum number of top female voices to return.

    Returns:
        A dictionary: {'male': [(name, id, likes), ...], 'female': [(name, id, likes), ...]}
        Returns empty lists if an error occurs or no voices are found.
    """
    print(f"Fetching available voices from ElevenLabs (aiming for top {num_male} male, {num_female} female)...")
    male_voices = []
    female_voices = []

    try:
        # Fetch all available voices (premade & cloned)
        all_voices_response = client.voices.get_all()

        if not all_voices_response or not hasattr(all_voices_response, 'voices'):
            print("Warning: Could not retrieve voices or response format unexpected.")
            return {'male': [], 'female': []}

        all_voices = all_voices_response.voices
        print(f"Found {len(all_voices)} total voices. Filtering and sorting...")

        # --- Filtering and Data Collection ---
        for voice in all_voices:
            # Default values
            gender = "unknown"
            is_english = False
            is_available = False # Start assuming not available unless checks pass
            likes = 0
            name = getattr(voice, 'name', 'Unnamed Voice')
            voice_id = getattr(voice, 'voice_id', None)

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
            # Fallback: check accent label if verified_languages isn't present/useful
            elif not is_english and voice.labels and isinstance(voice.labels, dict):
                 accent = voice.labels.get("accent", "").lower()
                 if accent in ["american", "british", "australian", "english", "uk", "us"]:
                      is_english = True

            # 3. Check if usable and get likes
            if hasattr(voice, 'sharing') and voice.sharing is not None:
                 # Assuming 'enabled_in_library' is a relevant check for general usability
                 is_available = getattr(voice.sharing, 'enabled_in_library', True)
                 # Attempt to get like count
                 likes = getattr(voice.sharing, 'liked_by_count', 0)
                 # Ensure likes is an integer if found
                 if not isinstance(likes, int):
                     likes = 0
            else:
                 # If no sharing info, assume it's a basic/premade voice and is available
                 is_available = True
                 likes = 0 # No like count expected/available for these

            # --- Apply Filters ---
            if is_english and is_available:
                 # Store as dictionary for slightly better JSON readability later
                 voice_data = {"name": name, "id": voice_id, "likes": likes}
                 if gender == "male":
                     male_voices.append(voice_data)
                 elif gender == "female":
                     female_voices.append(voice_data)

        print(f"Found {len(male_voices)} potential English male voices and {len(female_voices)} potential English female voices.")

        # Sort by 'likes' descending
        male_voices.sort(key=lambda x: x["likes"], reverse=True)
        female_voices.sort(key=lambda x: x["likes"], reverse=True)

        # Get the top N
        # Storing as list of dictionaries now
        top_male = male_voices[:num_male]
        top_female = female_voices[:num_female]

        # Return dictionary containing lists of dictionaries
        return {"male": top_male, "female": top_female}

    except Exception as e:
        print(f"Error fetching or processing ElevenLabs voices: {e}")
        return {'male': [], 'female': []}

def save_voices_to_json(voices_data: dict, filename: str):
    """Saves the voice data dictionary to a JSON file."""
    try:
        print(f"Attempting to save voice data to {filename}...")
        with open(filename, 'w', encoding='utf-8') as f:
            # Use indent for pretty printing
            json.dump(voices_data, f, ensure_ascii=False, indent=4)
        print(f"Successfully saved voice data to {filename}")
    except IOError as e:
        print(f"Error: Could not write to file {filename}. Reason: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while saving to JSON: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    load_dotenv()
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    if not ELEVENLABS_API_KEY:
        print("Error: ELEVENLABS_API_KEY not found in .env file or environment variables.")
        exit(1)

    parser = argparse.ArgumentParser(
        description="Fetch top English voices from ElevenLabs and save them to a JSON file."
        )
    parser.add_argument(
        "-n", "--num_voices",
        type=int,
        default=15,
        help="Number of top voices per gender to fetch (default: 15)."
        )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="elevenlabs_voices.json", # Sensible default filename
        help="Path to the output JSON file (default: elevenlabs_voices.json)."
        )
    args = parser.parse_args()

    try:
        print("Initializing ElevenLabs client...")
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("Client initialized.")
    except Exception as e:
        print(f"Error: Failed to initialize ElevenLabs client: {e}")
        exit(1)

    # Fetch the voices
    available_voices = get_elevenlabs_voices(client, num_male=args.num_voices, num_female=args.num_voices)

    # Save the fetched voices to the specified JSON file
    if available_voices and (available_voices.get('male') or available_voices.get('female')):
         save_voices_to_json(available_voices, args.output)
    else:
         print("No voice data fetched, skipping save.")
         # Optionally save an empty structure if desired
         # save_voices_to_json({'male': [], 'female': []}, args.output)


    # Display the results (Optional - can be commented out if only saving is needed)
    print("\n--- Top English Male Voices (Sorted by Likes) ---")
    if available_voices.get('male'):
        # Access data as dictionaries now
        for i, voice_info in enumerate(available_voices['male']):
            print(f"{i+1:2d}. Name: {voice_info['name']:<20} ID: {voice_info['id']:<25} Likes: {voice_info['likes']}")
    else:
        print("No male voices found matching criteria.")

    print("\n--- Top English Female Voices (Sorted by Likes) ---")
    if available_voices.get('female'):
        for i, voice_info in enumerate(available_voices['female']):
            print(f"{i+1:2d}. Name: {voice_info['name']:<20} ID: {voice_info['id']:<25} Likes: {voice_info['likes']}")
    else:
        print("No female voices found matching criteria.")

    print("\nVoice fetching and saving process complete.")
    print(f"Data saved to: {args.output}")