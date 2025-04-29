# --- START OF MODIFIED voice_selector.py ---

import os
import json
import random
import time
from typing import Dict, List, Tuple, Optional # Added Optional and Tuple

# Import the correct TTS module's get_voices function based on config
try:
    if os.path.exists('config.py'): # Basic check if config exists
        import config # Import config to read TTS_PROVIDER
        if config.TTS_PROVIDER == 'elevenlabs':
            from tts_elevenlabs import get_voices
            DEFAULT_FALLBACK = config.DEFAULT_FALLBACK_VOICE_ID
        elif config.TTS_PROVIDER == 'google':
            from tts_google import get_voices
            DEFAULT_FALLBACK = config.DEFAULT_FALLBACK_VOICE_ID
        elif config.TTS_PROVIDER == 'openai':
            from tts_openai import get_voices
            DEFAULT_FALLBACK = config.DEFAULT_FALLBACK_VOICE_ID
        else:
            print(f"Warning [VoiceSelector]: Unknown TTS_PROVIDER '{config.TTS_PROVIDER}' in config. Cannot load specific voices.")
            get_voices = lambda: {'male': [], 'female': []} # Dummy function
            DEFAULT_FALLBACK = ""
    else:
        print("Warning [VoiceSelector]: config.py not found. Cannot determine TTS provider or load voices.")
        get_voices = lambda: {'male': [], 'female': []} # Dummy function
        DEFAULT_FALLBACK = ""

except ImportError as e:
    print(f"Warning [VoiceSelector]: Failed to import TTS module or get_voices function: {e}. Voice selection might be limited.")
    get_voices = lambda: {'male': [], 'female': []} # Dummy function
    DEFAULT_FALLBACK = "" # No fallback if import fails
except Exception as e:
    print(f"Warning [VoiceSelector]: An unexpected error occurred during TTS module import: {e}")
    get_voices = lambda: {'male': [], 'female': []} # Dummy function
    DEFAULT_FALLBACK = ""

class VoiceSelector:
    """Manages voice selection, assignment, and persistence."""

    def __init__(self, voices_path: str, mapping_path: str):
        self.voices_path = voices_path
        self.mapping_path = mapping_path
        # Structure: {'male': [{'id': '...', 'name': '...'}], 'female': [...]}
        self.available_voices: Dict[str, List[Dict[str, str]]] = {'male': [], 'female': []}
        # Structure: {'Character Name': {'voice_id': '...', 'persona_instructions': '...'}}
        self.character_map: Dict[str, Dict[str, str]] = {}
        self.needs_saving = False

    def load_voices(self, force_refresh: bool = False):
        """Loads available voices from cache or fetches fresh from TTS provider."""
        if not force_refresh and os.path.exists(self.voices_path):
            try:
                with open(self.voices_path, 'r', encoding='utf-8') as f:
                    self.available_voices = json.load(f)
                print(f"Loaded {len(self.available_voices.get('male',[]))} male and {len(self.available_voices.get('female',[]))} female voices from cache: {self.voices_path}")
                if not self.available_voices.get('male') and not self.available_voices.get('female'):
                     print("Warning: Voice cache file is empty or invalid. Forcing refresh.")
                     self._fetch_and_cache_voices() # Force refresh if cache is bad
                return
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading voice cache file '{self.voices_path}': {e}. Fetching fresh voices.")
                self._fetch_and_cache_voices()
        else:
            print("No voice cache found or refresh forced. Fetching fresh voices...")
            self._fetch_and_cache_voices()

    def _fetch_and_cache_voices(self):
        """Fetches voices using the imported get_voices and caches them."""
        try:
            self.available_voices = get_voices()
            # Ensure cache directory exists
            os.makedirs(os.path.dirname(self.voices_path), exist_ok=True)
            with open(self.voices_path, 'w', encoding='utf-8') as f:
                json.dump(self.available_voices, f, indent=2)
            print(f"Successfully fetched and cached {len(self.available_voices.get('male',[]))} male and {len(self.available_voices.get('female',[]))} female voices to: {self.voices_path}")
        except Exception as e:
            print(f"Error fetching or caching voices: {e}")
            # Keep potentially outdated list or empty list if first time
            if not self.available_voices:
                 self.available_voices = {'male': [], 'female': []}

    def load_map(self):
        """Loads the character-to-voice mapping from file."""
        if os.path.exists(self.mapping_path):
            try:
                with open(self.mapping_path, 'r', encoding='utf-8') as f:
                    loaded_map = json.load(f)
                    # Validate and ensure persona field exists
                    validated_map = {}
                    for name, data in loaded_map.items():
                        if isinstance(data, dict) and 'voice_id' in data:
                             validated_map[name] = {
                                 'voice_id': data['voice_id'],
                                 'persona_instructions': data.get('persona_instructions', '') # Add default if missing
                             }
                        elif isinstance(data, str): # Handle old format maybe?
                             print(f"Warning: Found old map format for '{name}'. Resetting persona.")
                             validated_map[name] = {'voice_id': data, 'persona_instructions': ''}
                    self.character_map = validated_map
                print(f"Loaded {len(self.character_map)} character voice mappings from: {self.mapping_path}")
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading character map file '{self.mapping_path}': {e}. Starting with empty map.")
                self.character_map = {}
        else:
            print("No character map file found. Starting with empty map.")
            self.character_map = {}

    def save_map(self):
        """Saves the character-to-voice mapping to file if changes were made."""
        if self.needs_saving:
            try:
                # Ensure map directory exists
                os.makedirs(os.path.dirname(self.mapping_path), exist_ok=True)
                with open(self.mapping_path, 'w', encoding='utf-8') as f:
                    json.dump(self.character_map, f, indent=2)
                print(f"Character voice mapping file saved: {self.mapping_path}")
                self.needs_saving = False
            except IOError as e:
                print(f"Error saving character map file '{self.mapping_path}': {e}")
        # else:
        #     print("No changes to character map needed saving.")


    def load_data(self, force_refresh_voices: bool = False):
         """Loads both voices and mappings."""
         self.load_voices(force_refresh=force_refresh_voices)
         self.load_map()

    def find_or_assign_voice(self, character_name: str, gender: str, new_persona_instructions: str = "") -> Tuple[Optional[str], Optional[str]]:
        """
        Finds the existing voice and persona for a character, or assigns a new voice
        and stores the provided persona instructions.

        Args:
            character_name: The name of the character.
            gender: The gender ("Male", "Female", or "Unknown").
            new_persona_instructions: The persona instructions generated by Gemini
                                      (only used if the character is new).

        Returns:
            A tuple containing (voice_id, persona_instructions).
            Returns (None, None) if no suitable voice can be found/assigned.
        """
        if character_name == "Unknown":
             print("Character name is 'Unknown'. Using default fallback voice and no persona.")
             # Return fallback ID and empty persona
             return DEFAULT_FALLBACK or None, "" # Return fallback or None if no fallback set

        # 1. Check if character already exists
        if character_name in self.character_map:
            existing_data = self.character_map[character_name]
            voice_id = existing_data.get('voice_id')
            persona = existing_data.get('persona_instructions', '') # Get existing persona
            print(f"Found existing voice mapping for '{character_name}': {voice_id}")
            if persona:
                print(f"  -> Using stored persona.") # Don't print the whole persona here
            return voice_id, persona

        # 2. Character is new, assign a voice and store persona
        print(f"No existing voice mapping found for '{character_name}'. Assigning new voice...")
        assigned_voice_id = None
        assigned_voice_name = "N/A" # For printing

        # Determine which list of voices to use
        gender_key = gender.lower() if gender in ["Male", "Female"] else None
        voice_list = []
        if gender_key:
            voice_list = self.available_voices.get(gender_key, [])

        # Fallback to opposite gender or combined list if primary is empty
        if not voice_list:
            print(f"Warning: No voices available for specified gender '{gender}'. Trying opposite or combined list.")
            opposite_gender_key = 'female' if gender_key == 'male' else 'male'
            voice_list = self.available_voices.get(opposite_gender_key, [])
            if not voice_list: # If still empty, try combining all
                 voice_list = self.available_voices.get('male', []) + self.available_voices.get('female', [])

        # Filter out already used voices
        used_voice_ids = {data['voice_id'] for data in self.character_map.values()}
        available_pool = [v for v in voice_list if v['id'] not in used_voice_ids]

        if available_pool:
            selected_voice = random.choice(available_pool)
            assigned_voice_id = selected_voice['id']
            assigned_voice_name = selected_voice['name']
            print(f"Assigned new {gender or 'Unknown Gender'} voice: {assigned_voice_name} ({assigned_voice_id})")
        else:
            # No unused voices, maybe reuse one? Or use fallback?
            print(f"Warning: No unused voices available for {gender}. Attempting to reuse or use fallback.")
            # Option 1: Reuse a random voice from the original list (if any exist)
            if voice_list:
                 selected_voice = random.choice(voice_list)
                 assigned_voice_id = selected_voice['id']
                 assigned_voice_name = selected_voice['name']
                 print(f"Reusing voice: {assigned_voice_name} ({assigned_voice_id})")
            # Option 2: Use default fallback if reuse failed
            elif DEFAULT_FALLBACK:
                 assigned_voice_id = DEFAULT_FALLBACK
                 assigned_voice_name = f"Default Fallback ({DEFAULT_FALLBACK})"
                 print(f"Using default fallback voice: {assigned_voice_id}")
            else:
                 print("Error: No voices available and no fallback configured. Cannot assign voice.")
                 return None, None # Cannot assign

        # Store the new mapping with the provided persona instructions
        self.character_map[character_name] = {
            'voice_id': assigned_voice_id,
            'persona_instructions': new_persona_instructions or "" # Store empty if none provided
        }
        self.needs_saving = True
        if new_persona_instructions:
            print(f"  -> Stored newly generated persona for '{character_name}'.")
        else:
            print(f"  -> No persona instructions provided or generated for new character '{character_name}'. Stored empty.")


        return assigned_voice_id, new_persona_instructions or ""


# --- END OF MODIFIED voice_selector.py ---