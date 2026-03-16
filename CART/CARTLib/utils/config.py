import json
from abc import ABC, abstractmethod, ABCMeta
from pathlib import Path
import re
from typing import Generic, Optional, TypeVar, Callable

import qt

from . import CART_PATH, CART_VERSION

# The location of the default config used by a fresh installation of CART.
#  DO NOT TOUCH IT UNLESS YOU KNOW WHAT YOU'RE DOING.
DEFAULT_FILE = Path(__file__).parent / "default_config.json"
JOB_PROFILE_DIR = CART_PATH / "job_profiles"

# The location of the config file for this installation of CART.
GLOBAL_CONFIG_PATH = CART_PATH / "configuration.json"


## Re-Usable Abstract Elements ##
class DictBackedConfig(ABC):

    CONFIG_KEY = None

    def __init__(
            self,
            parent_config: Optional["DictBackedConfig"] = None,
            config_key_override: Optional[str] = None
    ):
        # Track the parent config
        self.parent_config: "DictBackedConfig" = parent_config

        # If a config label was provided, use it instead of our classmethod
        if config_key_override:
            self.config_label = config_key_override
        else:
            self.config_label = self.default_config_label()

        # Get (or generate) a backing dict
        if self.parent_config:
            # If the parent exists, ensure the backing dict is embedded within it
            self._backing_dict = parent_config.get_or_default(self.config_label, {})
        else:
            # Otherwise, use a standalone dict
            self._backing_dict = {}

        # Whether the contents of this config has been changed since creation
        self._has_changed = False

    @property
    def has_changed(self) -> bool:
        return self._has_changed

    @has_changed.setter
    def has_changed(self, new_state: bool):
        # Update our own state
        self._has_changed = new_state

        # If we've changed, mark every parent as having changed as well
        if new_state and self.parent_config:
            self.parent_config.has_changed = new_state

    @property
    def backing_dict(self) -> dict:
        return self._backing_dict

    @backing_dict.setter
    def backing_dict(self, new_dict: dict):
        """
        The backing dictionary for this Config.

        NOTE: The setter for this attribute does NOT change `has_changed` in any
        way; you should change it to match the context of why you overwrote the
        backing dict directly (i.e. setting it to "False" when you're resetting to
        a previous state).
        """
        # KO: To prevent de-sync with the parent config, replace the contents of
        #  our backing dict with the new dicts contents (instead of replacing
        #  the dictionary itself)
        self._backing_dict.clear()
        for k, v in new_dict.items():
            self._backing_dict[k] = v

    @classmethod
    @abstractmethod
    def default_config_label(cls) -> str:
        """
        Should return a string denoting the type of Config this is.

        Used to create child entries within parent configurations, as
        well as to help with debugging.
        """
        ...

    def get_or_default(self, key: str, default):
        """
        Gets a specific value from backing dict; if it doesn't exist,
        initializes the key in the dict to the default value provided,
        and returns it instead.
        """
        # Try to get the specified value
        val = self._backing_dict.get(key, None)

        # If it didn't exist, set it to our default and make a logged note
        if val is None:
            print(f"No '{key}' entry existed, setting it to {default}.")
            val = default
            self._backing_dict[key] = val
            self.has_changed = True

        return val

    @abstractmethod
    def show_gui(self) -> None:
        """
        Should show a dialogue prompt to the user, allowing them to change
        the configuration values managed by this Config object.
        """
        ...

    def save_without_parent(self) -> None:
        """
        Override if you want the save to go through when this
        Config instance lacks a parent to delegate too
        """
        raise NotImplementedError(
            f"Could not save DictBackedConfig instance of type '{self.__name__}'; "
            f"It does not have an '_save_without_parent' implementation, "
            f"and had no parent instance to delegate too."
        )

    def save(self) -> None:
        """
        Delegate to the parent configuration if possible
        """
        # Only save if our state has changed
        if not self.has_changed:
            return

        # If we have a parent config, have it save instead
        if self.parent_config:
            self.parent_config.save()
        else:
            self.save_without_parent()

        # Mark ourselves as no longer having changes from the file
        self.has_changed = False


# I love Metaclass conflicts! Wooo!
class _ABCQDialog(type(qt.QDialog), ABCMeta):
    ...


# Generic type for DictBackedConfig subclasses
DICT_CONFIG_TYPE = TypeVar("DICT_CONFIG_TYPE", bound=DictBackedConfig)


class ConfigDialog(qt.QDialog, ABC, Generic[DICT_CONFIG_TYPE], metaclass=_ABCQDialog):
    """
    QT Dialog built to be paired with a DictBackConfig.

    Provides some shared utilities to streamline the creation of a
    Config GUI, including:
      * Resetting the bound Config when the user backs out
      * Allow the user to reset the Config state explicitly
      * Asking the user if they want to save if they close the GUI
       after making changes
    """
    def __init__(self, bound_config: DICT_CONFIG_TYPE):
        # Initialize the QT Dialogue first
        super().__init__()

        # Track the bound config so we can modify it later
        self.bound_config: DICT_CONFIG_TYPE = bound_config

        # Track a copy of that config's backing dict as a backup
        self._restore_dict = bound_config.backing_dict.copy()

        # The layout which the user should place their widgets within
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Track a list of "sync" functions; each is called
        # iteratively when a synchronization is done
        self._sync_func_list: dict[qt.QWidget, list[Callable[[], None]]] = dict()

        # Build the GUI
        self.buildGUI(layout)

        # Add a suite of buttons w/ standardized functionality
        self._addButtons(layout)

        # Sync the GUI to match the config
        self.sync()

    ## GUI Elements ##
    @abstractmethod
    def buildGUI(self, layout: qt.QFormLayout):
        """
        Add any QT widgets to the GUI here; ensures that they are placed
        appropriately within the dialogue (namely, above the button panel)
        """
        ...

    def _addButtons(self, layout: qt.QFormLayout):
        # The button box itself
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Reset | qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )

        # Function to map the button press to our functionality
        def onButtonPressed(button: qt.QPushButton):
            # Get the role of the button
            button_role = buttonBox.buttonRole(button)
            # Match it to our corresponding function
            # TODO: Replace this with a `match` statement when porting to Slicer 5.9
            if button_role == qt.QDialogButtonBox.AcceptRole:
                self.onConfirm()
            elif button_role == qt.QDialogButtonBox.RejectRole:
                self.onCancel()
            elif button_role == qt.QDialogButtonBox.ResetRole:
                self.onReset()
            else:
                raise ValueError("Pressed a button with an invalid role somehow...")

        buttonBox.clicked.connect(onButtonPressed)

        layout.addRow(buttonBox)

    ## Config Synchronization ##
    def register_sync_function(self, widget: qt.QWidget, func: Callable[[], None]):
        """
        Register a synchronization function to be associated with a given widget
        """
        func_list = self._sync_func_list.get(widget, [])
        func_list.append(func)
        self._sync_func_list[widget] = func_list

    def sync(self):
        """
        Runs each registered sync function in turn, synchronizing their state with the
        GUI (however the registered function chose to do so) while blocking signals
        from the associated widget in the process (to prevent redundant config update
        calls).
        """
        for widget, func_list in self._sync_func_list.items():
            widget.blockSignals(True)
            for f in func_list: f()
            widget.blockSignals(False)

    ## User Interactions ##
    def onConfirm(self):
        """
        Called when the user confirms the changes they made (if any).
        """
        self.bound_config.save()
        self.accept()

    def onCancel(self):
        """
        Called when the user tries to cancel out of the prompt w/o saving.
        """
        # If the user hasn't made any changes, just close
        if not self.bound_config.has_changed:
            self.accept()
            return

        # Prompt the user if they made changes they may want to save
        reply = qt.QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have not saved your changes; would you like to now?",
            qt.QMessageBox.Yes, qt.QMessageBox.No
        )

        # Save to file only if the user confirms it
        if reply == qt.QMessageBox.Yes:
            self.bound_config.save()
            self.accept()
        else:
            self.bound_config.backing_dict = self._restore_dict
            self.bound_config.has_changed = False
            self.reject()

    def onReset(self):
        """
        Called when the user explicitly requests the config be reset
        """
        self.bound_config.backing_dict = self._restore_dict
        self.sync()
        self.bound_config.has_changed = False

    ## QT Events ##
    def closeEvent(self, event):
        """
        Intercepts when the user closes the window by clicking the 'x' in the
        dialog; ensures any modifications don't get discarded by mistake.
        """
        self.onCancel()
        event.accept()


## Backing Config Managers ##
class MasterProfileConfig(DictBackedConfig):
    ## Attributes ##
    AUTHOR_KEY = "author"

    @property
    def author(self) -> Optional[str]:
        return self.backing_dict.get(self.AUTHOR_KEY, None)

    @author.setter
    def author(self, new_author: str):
        self.backing_dict[self.AUTHOR_KEY] = new_author
        self.has_changed = True

    POSITION_KEY = "position"

    @property
    def position(self) -> Optional[str]:
        return self.backing_dict.get(self.POSITION_KEY, None)

    @position.setter
    def position(self, new_position):
        self.backing_dict[self.POSITION_KEY] = new_position
        self.has_changed = True

    @position.setter
    def position(self, new_position):
        self.backing_dict[self.POSITION_KEY] = new_position
        self.has_changed = True

    REGISTERED_JOB_KEY = "registered_jobs"

    @property
    def registered_jobs(self) -> dict[str, str]:
        """
        Map of registered jobs, in "name: path" format.
        """
        job_map = self.get_or_default(self.REGISTERED_JOB_KEY, {})
        return job_map

    def register_new_job(self, job_config: "JobProfileConfig"):
        # Register the new job
        k = job_config.name
        p = str(job_config.file.resolve())
        job_map = self.get_or_default(self.REGISTERED_JOB_KEY, {})
        job_map[k] = p
        # Mark ourselves as being changed
        self.has_changed = True

    @property
    def last_job(self) -> Optional[tuple[str, Path]]:
        """
        Returns the name and path to the job last used, as detailed within this config.
        """
        job_registry = self.registered_jobs
        if len(self.registered_jobs) < 1:
            return None
        first_key = next(iter(job_registry.keys()))
        return first_key, job_registry[first_key]

    def set_last_job(self, job_name: str):
        old_job_registry = self.get_or_default(self.REGISTERED_JOB_KEY, {})
        job_path = old_job_registry.get(job_name, None)
        if job_path is None:
            raise ValueError(
                f"Job '{job_name}' has not been registered! Cannot make it the last-used job."
            )
        # Re-build our job map using the new setup
        new_registry = {job_name: job_path}
        for k, v in old_job_registry.items():
            # Skip adding the job again; it's already inserted
            if k == job_name:
                continue
            new_registry[k] = v
        self.backing_dict[self.REGISTERED_JOB_KEY] = new_registry
        self.has_changed = True

    VERSION_KEY = "version"

    @property
    def version(self):
        return self.get_or_default(self.VERSION_KEY, CART_VERSION)

    @version.setter
    def version(self, new_version: str):
        """
        WARNING: You really shouldn't change this yourself. The version
        used
        """
        self.backing_dict[self.VERSION_KEY] = new_version

    REGISTERED_TASK_PATHS_KEY = "registered_task"

    @property
    def registered_task_paths(self) -> Optional[dict[str, Path]]:
        registered_task_vals: dict[str, str]  = self.backing_dict.get(self.REGISTERED_TASK_PATHS_KEY)
        if registered_task_vals is None:
            return None
        return_dict = {}
        for k, v in registered_task_vals.items():
            p = Path(v)
            if not p.is_file():
                print(f"WARNING: Task file '{v}' does not exist!")
                return_dict[k] = None
            else:
                return_dict[k] = p
        return return_dict

    def add_task_path(self, task_name: str, task_path: Path):
        registered_task_vals = self.get_or_default(self.REGISTERED_TASK_PATHS_KEY, {})
        registered_task_vals[task_name] = str(task_path.resolve())
        self.has_changed = True

    def clear_task_paths(self):
        # Clear the task paths entirely!
        self.backing_dict[self.REGISTERED_TASK_PATHS_KEY] = {}
        self.has_changed = True

    ## Utilities ##
    def save_without_parent(self) -> None:
        """
        Save the in-memory contents of the configuration back to our JSON file
        """
        with open(GLOBAL_CONFIG_PATH, "w") as fp:
            json.dump(self.backing_dict, fp, indent=2)

    def reload(self):
        if not GLOBAL_CONFIG_PATH.exists():
            print(f"Could not load master config; configuration file does not exist!")
            return
        with open(GLOBAL_CONFIG_PATH, "r") as fp:
            self.backing_dict = json.load(fp)

    def show_gui(self) -> qt.QDialog:
        # TODO
        pass

    @classmethod
    def default_config_label(cls) -> str:
        return "cart_master_profile"


class JobProfileConfig(DictBackedConfig):
    NAME_KEY = "name"

    def __init__(
            self,
            parent_config: Optional["DictBackedConfig"] = None,
            config_key_override: Optional[str] = None,
            file_path: Optional[Path] = None
    ):
        super().__init__(parent_config, config_key_override)

        self._file_path = file_path

    @property
    def name(self) -> Optional[str]:
        return self.backing_dict.get(self.NAME_KEY, None)

    @name.setter
    def name(self, new_name: str):
        # Flip backslashes to prevent horrific bugs
        new_name = new_name.replace("\\", "/")
        self.backing_dict[self.NAME_KEY] = new_name
        self.has_changed = True

    DATA_PATH_KEY = "data_path"

    @property
    def data_path(self) -> Optional[Path]:
        path_str = self.get_or_default(self.DATA_PATH_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @data_path.setter
    def data_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.DATA_PATH_KEY] = path_str
        self.has_changed = True

    OUTPUT_PATH_KEY = "output_path"

    @property
    def output_path(self) -> Optional[Path]:
        path_str = self.get_or_default(self.OUTPUT_PATH_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @output_path.setter
    def output_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.OUTPUT_PATH_KEY] = path_str
        self.has_changed = True

    COHORT_FILE_KEY = "cohort_file"

    @property
    def cohort_path(self) -> Optional[Path]:
        path_str = self.backing_dict.get(self.COHORT_FILE_KEY, None)
        if path_str is None:
            return None
        return Path(path_str)

    @cohort_path.setter
    def cohort_path(self, new_path: Path):
        path_str = str(new_path)
        self.backing_dict[self.COHORT_FILE_KEY] = path_str
        self.has_changed = True

    TASK_KEY = "task"

    @property
    def task(self) -> str:
        return self.get_or_default(self.TASK_KEY, None)

    @task.setter
    def task(self, new_task: str):
        self._backing_dict[self.TASK_KEY] = new_task
        self.has_changed = True

    ## Abstract Methods ##
    @classmethod
    def default_config_label(cls) -> str:
        return "job_profile"

    def show_gui(self) -> None:
        pass

    ## File I/O ##
    @property
    def file(self) -> Path:
        """
        The file this configuration will be saved to.

        Get-only to encourage the file name to be the similar to
        the job's name if at all possible
        """
        if self._file_path:
            return self._file_path
        else:
            # This is to keep Windows from having a stroke + backslashes begone
            cleaned_name = re.sub('[<>:"/|?*\\\\]', '-', self.name)
            # Replace spaces with underscores for cleanliness’s sake
            cleaned_name = cleaned_name.replace(" ", "_")
            # Keep adding underscores until file collision is resolved:
            # KO: This is very quick-and-dirty, but given the small number of
            #  collisions likely to occur, this is more than enough.
            suffix = ""
            while True:
                # Format the job name to create a potential filename
                new_file = JOB_PROFILE_DIR / f"{cleaned_name}{suffix}.json"
                # If this file already exists, continue to the next loop
                if new_file.exists():
                    suffix += "_"
                    continue
                # Otherwise, track this file and return
                self._file_path = new_file
                return new_file

    def reload(self):
        """
        (Re-)loads config's contents into memory.
        """
        # If there's no config file yet, there's nothing to load
        if not self.file.exists():
            print("Nothing to load!")
            return
        # Otherwise,
        with open(self.file, 'r') as fp:
            new_data = json.load(fp)
            self.backing_dict = new_data

    def save_without_parent(self) -> None:
        # Save this config to file.
        self.file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file, 'w') as fp:
            json.dump(self.backing_dict, fp, indent=2)
