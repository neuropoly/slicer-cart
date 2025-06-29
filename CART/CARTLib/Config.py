import json
from pathlib import Path

# The location of the default config used by a fresh installation of CART.
#  DO NOT TOUCH IT UNLESS YOU KNOW WHAT YOU'RE DOING.
DEFAULT_FILE = Path(__file__).parent / "default_config.json"

# The location of the config file for this installation of CART.
CONFIG_FILE = Path(__file__).parent.parent / "configuration.json"


class Config:
    """
    Configuration manager for CART.
    """
    # Contains the actual configuration values, loaded from and saved to JSON
    _config_dict: dict = {}

    # Whether a change has been made to the config that the user might want to save
    _has_changed: bool = False

    ## I/O ##
    @classmethod
    def load(cls):
        """
        (Re-)Load the configuration from the file.

        Does NOT check whether the user has unsaved changes; that should be
        handled by the logic requesting the configuration be loaded!
        """
        # If the configuration file doesn't exist, copy our default to make one
        if not CONFIG_FILE.exists():
            print("No configuration file found, creating a new one!")
            with open(DEFAULT_FILE, "r") as cf:
                # Load the data
                cls._config_dict = json.load(cf)
                # And immediately save it, creating a copy
                cls.save()
        # Otherwise, load the configuration as-is
        else:
            with open(CONFIG_FILE, "r") as cf:
                cls._config_dict = json.load(cf)

        # Mark that there are no longer any changes between the config and file
        cls._has_changed = False

    @classmethod
    def save(cls):
        """
        Save the in-memory contents of the configuration back to our JSON file
        """
        with open(CONFIG_FILE, "w") as cf:
            json.dump(cls._config_dict, cf, indent=2)

        # Mark that there are no longer any changes between the config and file
        cls._has_changed = False

    @classmethod
    def get_users(cls) -> list[str]:
        key = "users"
        # Attempt to get the users entry
        user_entry = cls._config_dict.get(key, None)

        # If it didn't exist, add an empty list instead
        if user_entry is None:
            user_entry = []
            print(f"No '{key}' entry existed, setting it to {user_entry}.")
            cls._config_dict[key] = user_entry
            cls._has_changed = True

        # Otherwise, return it as-is
        return user_entry
