import random
import config # Import config for fallback ID and paths
import data_manager

class VoiceSelector:
    """Handles loading voice data and assigning voices to characters locally."""

    def __init__(self, voices_filepath: str, mapping_filepath: str):
        self.voices_filepath = voices_filepath
        self.mapping_filepath = mapping_filepath
        self.available_voices: dict = {'male': [], 'female': []} # Standardized format
        self.character_voice_map: dict = {}
        self.assigned_voice_ids: set = set()
        self.map_updated: bool = False
        self.fallback_voice_id: str = config.DEFAULT_FALLBACK_VOICE_ID

    def load_data(self):
        """Loads available voices and the current character-voice map."""
        print(f"Loading available voices from: {self.voices_filepath}")
        self.available_voices = data_manager.load_json_data(
            self.voices_filepath, default={'male': [], 'female': []}
        )
        # Basic validation of loaded voice data structure
        if not isinstance(self.available_voices, dict) or \
           not all(k in self.available_voices for k in ['male', 'female']) or \
           not isinstance(self.available_voices['male'], list) or \
           not isinstance(self.available_voices['female'], list):
            print(f"Warning: Invalid format in {self.voices_filepath}. Expected {{'male': [...], 'female': [...]}}. Using empty lists.")
            self.available_voices = {'male': [], 'female': []}

        print(f"Loading character voice map from: {self.mapping_filepath}")
        self.character_voice_map = data_manager.load_json_data(
            self.mapping_filepath, default={}
        )

        # Populate assigned voice IDs from the loaded map
        self.assigned_voice_ids = set(self.character_voice_map.values())

        num_male = len(self.available_voices.get('male', []))
        num_female = len(self.available_voices.get('female', []))
        print(f"Loaded {num_male} male voices, {num_female} female voices.")
        print(f"Loaded {len(self.character_voice_map)} existing character voice mappings.")
        print("-" * 30)

    def find_or_assign_voice(self, character_name: str, gender: str) -> str | None:
        """
        Finds an existing voice mapping or assigns a new one based on gender.
        Returns the selected voice ID or the fallback ID if none can be assigned.
        Returns None only if fallback ID is also missing.
        """
        if not character_name or character_name == "Unknown":
            print("Character name is Unknown. Using default fallback voice.")
            return self.fallback_voice_id if self.fallback_voice_id else None

        map_key = character_name.lower() # Use lowercase for map keys

        if map_key in self.character_voice_map:
            selected_voice_id = self.character_voice_map[map_key]
            print(f"Found existing voice mapping for '{character_name}': {selected_voice_id}")
            return selected_voice_id
        else:
            print(f"No existing voice mapping found for '{character_name}'. Assigning new voice...")
            self.map_updated = True # Will need to save map if we assign

            # Determine pools based on gender
            primary_pool_key = None
            secondary_pool_key = None

            if gender == "Male":
                primary_pool_key = 'male'
                secondary_pool_key = 'female'
            elif gender == "Female":
                primary_pool_key = 'female'
                secondary_pool_key = 'male'
            else: # Unknown gender - try female first, then male
                print("Gender is Unknown. Trying female voices first, then male.")
                primary_pool_key = 'female'
                secondary_pool_key = 'male'

            primary_pool = self.available_voices.get(primary_pool_key, [])
            secondary_pool = self.available_voices.get(secondary_pool_key, [])

            assigned_id = None

            # --- Try Primary Pool ---
            unassigned_primary = [
                v for v in primary_pool if v.get('id') and v.get('id') not in self.assigned_voice_ids
            ]
            if unassigned_primary:
                # Simple assignment: pick the first available
                # Could add randomness: random.shuffle(unassigned_primary)
                chosen_voice_info = unassigned_primary[0]
                assigned_id = chosen_voice_info.get('id')
                print(f"Assigned new {gender if gender != 'Unknown' else primary_pool_key} voice: {chosen_voice_info.get('name', 'N/A')} ({assigned_id})")
            else:
                print(f"No unassigned voice found in the primary pool ({primary_pool_key}).")


            # --- Try Secondary Pool if Primary Failed ---
            if not assigned_id:
                 print(f"Trying secondary pool ({secondary_pool_key})...")
                 unassigned_secondary = [
                     v for v in secondary_pool if v.get('id') and v.get('id') not in self.assigned_voice_ids
                 ]
                 if unassigned_secondary:
                     # random.shuffle(unassigned_secondary)
                     chosen_voice_info = unassigned_secondary[0]
                     assigned_id = chosen_voice_info.get('id')
                     print(f"Assigned new secondary pool voice: {chosen_voice_info.get('name', 'N/A')} ({assigned_id})")
                 else:
                      print(f"No unassigned voice found in the secondary pool ({secondary_pool_key}).")

            # --- Assign and Update Map or Fallback ---
            if assigned_id:
                self.character_voice_map[map_key] = assigned_id
                self.assigned_voice_ids.add(assigned_id)
                return assigned_id
            else:
                print(f"Warning: Could not find an unassigned voice in available pools for '{character_name}'. Using fallback.")
                # Optional: Map the fallback to the character? Usually not desired.
                # self.character_voice_map[map_key] = self.fallback_voice_id
                # self.assigned_voice_ids.add(self.fallback_voice_id) # careful not to exhaust fallback if used repeatedly
                return self.fallback_voice_id if self.fallback_voice_id else None


    def save_map(self):
        """Saves the character-voice map to file if it has been updated."""
        if self.map_updated:
            print(f"\nUpdating character voice mapping file: {self.mapping_filepath}")
            data_manager.save_json_data(self.character_voice_map, self.mapping_filepath)
            self.map_updated = False # Reset flag after saving
        else:
            # print("No changes to the character voice map to save.")
            pass