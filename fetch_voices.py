import os
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv
import argparse

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
                 # Consider more accents if needed
                 if accent in ["american", "british", "australian", "english", "uk", "us"]:
                      is_english = True

            # 3. Check if usable (e.g., enabled in library - adjust based on your needs)
            # Let's assume most voices returned by get_all are usable unless specifically marked otherwise.
            # You might add more checks based on 'category', 'fine_tuning' status etc. if required.
            # For now, we rely mainly on language and gender.
            # Using sharing status can be helpful if available and relevant
            if hasattr(voice, 'sharing') and voice.sharing is not None:
                 is_available = getattr(voice.sharing, 'enabled_in_library', True) # Example check
                 likes = getattr(voice.sharing, 'liked_by_count', 0)
            else:
                 # If no sharing info, assume it's a basic/premade voice and is available
                 is_available = True
                 likes = 0 # No like count available

            # --- Apply Filters ---
            if is_english and is_available:
                 voice_data = {"name": name, "id": voice_id, "likes": likes}
                 if gender == "male":
                     male_voices.append(voice_data)
                 elif gender == "female":
                     female_voices.append(voice_data)
                 # You could add an 'unknown_gender' list if needed

        print(f"Found {len(male_voices)} potential English male voices and {len(female_voices)} potential English female voices.")

        # Sort by 'likes' descending
        male_voices.sort(key=lambda x: x["likes"], reverse=True)
        female_voices.sort(key=lambda x: x["likes"], reverse=True)

        # Get the top N, storing name, id, and likes
        top_male = [(v["name"], v["id"], v["likes"]) for v in male_voices[:num_male]]
        top_female = [(v["name"], v["id"], v["likes"]) for v in female_voices[:num_female]]

        return {"male": top_male, "female": top_female}

    except Exception as e:
        print(f"Error fetching or processing ElevenLabs voices: {e}")
        # Return empty lists on error
        return {'male': [], 'female': []}

# --- Main Execution ---
if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()

    # Get API key
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    if not ELEVENLABS_API_KEY:
        print("Error: ELEVENLABS_API_KEY not found in .env file or environment variables.")
        exit(1) # Exit if key is missing

    # Setup command-line argument parsing
    parser = argparse.ArgumentParser(description="Fetch and display top English voices from ElevenLabs.")
    parser.add_argument(
        "-n", "--num_voices",
        type=int,
        default=15,
        help="Number of top voices per gender to fetch and display (default: 15)."
        )
    args = parser.parse_args()

    # Initialize ElevenLabs Client
    try:
        print("Initializing ElevenLabs client...")
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print("Client initialized.")
    except Exception as e:
        print(f"Error: Failed to initialize ElevenLabs client: {e}")
        exit(1) # Exit if client fails to initialize

    # Fetch the voices
    available_voices = get_elevenlabs_voices(client, num_male=args.num_voices, num_female=args.num_voices)

    # Display the results
    print("\n--- Top English Male Voices (Sorted by Likes) ---")
    if available_voices['male']:
        for i, (name, voice_id, likes) in enumerate(available_voices['male']):
            print(f"{i+1:2d}. Name: {name:<20} ID: {voice_id:<25} Likes: {likes}")
    else:
        print("No male voices found matching criteria.")

    print("\n--- Top English Female Voices (Sorted by Likes) ---")
    if available_voices['female']:
        for i, (name, voice_id, likes) in enumerate(available_voices['female']):
            print(f"{i+1:2d}. Name: {name:<20} ID: {voice_id:<25} Likes: {likes}")
    else:
        print("No female voices found matching criteria.")

    print("\nVoice fetching complete.")