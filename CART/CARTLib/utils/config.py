import json
from abc import ABC, abstractmethod, ABCMeta
from contextlib import contextmanager
from pathlib import Path
from typing import Generic, Optional, TypeVar, Union

import qt

# The location of the default config used by a fresh installation of CART.
#  DO NOT TOUCH IT UNLESS YOU KNOW WHAT YOU'RE DOING.
DEFAULT_FILE = Path(__file__).parent / "default_config.json"


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

        # Build the GUI
        self.buildGUI(layout)

        # Add a suite of buttons w/ standardized functionality
        self._addButtons(layout)

        # Sync the GUI to match the config
        self._sync()

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
    @contextmanager
    def block_signals(self):
        layout = self.layout()
        widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
        for w in widgets:
            w.blockSignals(True)

        yield

        for w in widgets:
            w.blockSignals(False)

    def _sync(self):
        """
        Runs `sync` below, but blocks signals from widgets within the dialogue to
        prevent the widget's from emitting signals while they're being changed
        """
        with self.block_signals():
            self.sync()

    @abstractmethod
    def sync(self):
        """
        Synchronize the GUI with its bound config; this is done it two places:

        * When the GUI is initially created (after all widgets are added)
        * When the user clicks the "reset" button (after the Config's state is reset)

        If you override either of these actions
        """
        ...

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
        self._sync()
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
class ProfileConfig(DictBackedConfig):
    """
    Configuration manager for a CART profile.

    Tracks the profile's settings, allowing for profiles of
    settings to be swapped on the fly.
    """
    DEFAULT_ROLE = "N/A"

    def __init__(self, label: str, backing_dict: dict, parent_config: "CARTConfig"):
        # Init w/o a parent config initially
        super().__init__()

        # Explicitly set our inherited attributes instead;
        # needed as Users are not handled like regular Config entries
        self._backing_dict = backing_dict
        self.parent_config: "CARTConfig" = parent_config

        # As each profile gets its own config entry, each with a unique label
        self.config_label = label

    @classmethod
    def default_config_label(cls) -> str:
        # Profiles are stored in a profile dict, and use their own label
        # within said dict instead of a shared label.
        pass

    @property
    def label(self):
        return self.config_label

    ## Last Used Settings ##
    LAST_USED_COHORT_KEY = "last_used_cohort_file"

    @property
    def last_used_cohort_file(self) -> Union[Path, None]:
        val = self._backing_dict.get(self.LAST_USED_COHORT_KEY, None)
        if val is None:
            return None
        # noinspection PyUnreachableCode
        return Path(val)

    @last_used_cohort_file.setter
    def last_used_cohort_file(self, new_path: Path):
        self._backing_dict[self.LAST_USED_COHORT_KEY] = str(new_path)
        self.has_changed = True

    LAST_USED_DATA_KEY = "last_used_data_path"

    @property
    def last_used_data_path(self) -> Union[Path, None]:
        val = self._backing_dict.get(self.LAST_USED_DATA_KEY, None)
        if val is None:
            return None
        # noinspection PyUnreachableCode
        return Path(val)

    @last_used_data_path.setter
    def last_used_data_path(self, new_path: Path):
        self._backing_dict[self.LAST_USED_DATA_KEY] = str(new_path)
        self.has_changed = True

    LAST_USED_TASK_KEY = "last_used_task"

    @property
    def last_used_task(self) -> str:
        val = self._backing_dict.get(self.LAST_USED_TASK_KEY, "")
        return val

    @last_used_task.setter
    def last_used_task(self, new_task: str):
        self._backing_dict[self.LAST_USED_TASK_KEY] = new_task

    ## Profile Role ##
    ROLE_KEY = "role"

    @property
    def role(self) -> str:
        return self.get_or_default(self.ROLE_KEY, self.DEFAULT_ROLE)

    @role.setter
    def role(self, new_role: str):
        self._backing_dict[self.ROLE_KEY] = new_role
        self.has_changed = True

    @property
    def valid_roles(self) -> list[str]:
        return self.parent_config.profile_roles

    ## Autosaving Management ##
    SAVE_ON_ITER_KEY = "save_on_iter"

    @property
    def save_on_iter(self) -> bool:
        return self.get_or_default(self.SAVE_ON_ITER_KEY, True)

    @save_on_iter.setter
    def save_on_iter(self, new_val: bool):
        # Validate that the value is a boolean, to avoid weird jank later
        assert isinstance(new_val, bool), f"'{self.SAVE_ON_ITER_KEY}' must be a boolean value."
        self._backing_dict[self.SAVE_ON_ITER_KEY] = new_val
        self.has_changed = True

    ## Sub-Configurations ##
    SUB_CONFIGS_KEY = "sub_config"

    @property
    def sub_configs(self) -> dict:
        return self.get_or_default(self.SUB_CONFIGS_KEY, {})

    def get_sub_config(self, key: str):
        sub_entry = self.sub_configs.get(key, False)
        if not sub_entry:
            new_entry = {}
            self.sub_configs[key] = new_entry
            return new_entry
        else:
            return sub_entry

    ## Utils ##
    def show_gui(self):
        # Build the Config prompt
        prompt = ProfileConfigDialog(bound_config=self)
        # Show it, blocking other interactions until its resolved
        prompt.exec()

    def save(self):
        # If the selected role is new, add it to the config first
        if self.role not in self.parent_config.profile_roles:
            self.parent_config.profile_roles.append(self.role)

        super().save()


class CARTConfig(DictBackedConfig):
    """
    Global configuration for CART itself.

    Manages profiles, as well as tracking some simple metrics
    itself to allow for restoring the previous profile
    """
    DEFAULT_LABEL = "Default"
    CONFIG_KEY = "CART"

    def __init__(self, config_path: Path):
        # Initialize the dict-backed config attributes
        super().__init__()

        # Path to the file the config should be saved to
        self.config_path = config_path

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## Profile Management ##
    PROFILE_KEY = "user_profiles"
    DEFAULT_ROLES = [ProfileConfig.DEFAULT_ROLE]

    @property
    def profiles(self) -> dict[str, dict]:
        return self.get_or_default(self.PROFILE_KEY, {})

    def new_profile(
            self,
            label: str,
            new_settings: dict = None,
            reference_profile: ProfileConfig = None
    ) -> ProfileConfig:
        """
        Create a new profile, copying config entries from a
        reference profile if provided.

        :param label: The label for this new profile
        :param new_settings: Settings specified by the user that should be
            applied to this new profile
        :param reference_profile: Reference profile; any settings not specified
            in `new_settings` above will be copied from here.
        """
        # Confirm that the provided profile label is available and valid
        stripped_name = label.strip()
        if not stripped_name:
            raise ValueError("Cannot create a profile without a label!")

        if stripped_name in GLOBAL_CONFIG.profiles.keys():
            raise ValueError(f"Profile with label '{stripped_name}' already exists!")

        # If a reference profile was provided, use its settings as our base
        if reference_profile:
            new_profile = reference_profile.backing_dict.copy()
        # Otherwise, start with a blank slate
        else:
            new_profile = {}

        # We can have a set of settings to override as well, if provided
        if new_settings:
            for k, v in new_settings.items():
                new_profile[k] = v

        # Assign it into our profile dictionary
        self.profiles[label] = new_profile

        # Return the result, wrapped in our ProfileConfig
        return ProfileConfig(label, new_profile, self)

    def get_profile_config(self, label: str) -> Optional[ProfileConfig]:
        profile_dict = self.profiles.get(label, None)
        if profile_dict is not None:
            return ProfileConfig(label, profile_dict, self)
        else:
            return None

    def promptNewProfile(self, reference_profile: ProfileConfig = None) -> Optional[str]:
        """
        Generate a QT prompt for the user to create a new profile entry.

        :param reference_profile: The profile to copy configuration settings from (if any)

        :return: The label of the new profile; None if the user backed out.
        """
        # Try to generate a new profile from the provided reference
        prompt = NewProfileDialog(reference_profile, GLOBAL_CONFIG)
        profile_added_successfully = prompt.exec()

        # If successful, return the profile label for easy reference
        if profile_added_successfully:
            # Mark oneself as having changed
            self.has_changed = True
            # Return the new profile label for reference elsewhere
            return prompt.profile
        # Otherwise, return nothing
        else:
            return None

    LAST_PROFILE_KEY = "last_profile"

    @property
    def last_profile(self):
        return self.get_or_default(
            self.LAST_PROFILE_KEY, self.DEFAULT_LABEL
        )

    @last_profile.setter
    def last_profile(self, new_label: str):
        self._backing_dict[self.LAST_PROFILE_KEY] = new_label
        self.has_changed = True

    PROFILE_ROLES_KEY = "profile_roles"

    @property
    def profile_roles(self) -> list[str]:
        return self.get_or_default(self.PROFILE_ROLES_KEY, self.DEFAULT_ROLES)

    def new_profile_role(self, new_role: str):
        if new_role in self.profile_roles:
            raise ValueError(f"Role '{new_role}' already exists!")

        self.profile_roles.append(new_role)
        self.has_changed = True

    def show_gui(self):
        raise NotImplementedError("You should configure CART on a per-profile basis!")

    ## I/O ##
    def load_from_json(self):
        """
        (Re-)Load the configuration from the file.

        Does NOT check whether the user has unsaved changes; that should be
        handled by whatever is requesting the configuration be loaded!
        """
        # If our specified configuration file doesn't exist, copy the default to make one
        if not MAIN_CONFIG.exists():
            print("No configuration file found, creating a new one!")
            with open(DEFAULT_FILE) as cf:
                # Load the data
                self._backing_dict = json.load(cf)
                # And immediately save it, creating a copy
                self.save()
        # Otherwise, load the configuration as-is
        else:
            with open(self.config_path) as cf:
                self._backing_dict = json.load(cf)

    def save_without_parent(self):
        """
        Save the in-memory contents of the configuration back to our JSON file
        """
        with open(MAIN_CONFIG, "w") as cf:
            json.dump(self._backing_dict, cf, indent=2)


## GUI elements ##
class NewProfileDialog(qt.QDialog):
    def __init__(self, reference_profile: "ProfileConfig", master_config: "CARTConfig"):
        # Initialize the QDialog base itself
        super().__init__()

        # A reference config to copy from if the user requests it
        self.reference_profile = reference_profile

        # The master config we want to save the profile too
        self.master_config = master_config

        # The text field widget for the profile label
        self.profileLabelEdit: qt.QLineEdit = None

        # Selection field for the role
        self.roleComboBox: qt.QComboBox = None

        # Toggle box which make the profile a blank slate if checked
        # (instead of copying the active profile's state, the default)
        self.blankSlateBox: qt.QCheckBox = None

        # Track the button box so we can react to them being pressed
        self.buttonBox: qt.QDialogButtonBox = None

        # Built the GUI contents
        self.buildUI()

    ## GUI components ##
    def addButtons(self):
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )
        buttonBox.clicked.connect(self.onButtonPressed)
        return buttonBox

    def buildUI(self):
        # General window properties
        self.setWindowTitle("New Profile")

        # Create a form layout to hold everything in
        layout = qt.QFormLayout()
        self.setLayout(layout)

        # Add a field for submitting the profile label
        profileLabelEdit = qt.QLineEdit()
        profileLabelLabel = qt.QLabel("Label:")
        profileLabelLabel.setToolTip(
            "An ID label for this profile. Cannot match an existing profile label!"
        )
        self.profileLabelEdit = profileLabelEdit

        # Add them to our layout
        layout.addRow(profileLabelLabel, profileLabelEdit)

        # Add a combobox that lets the user select the profile's role
        roleComboBox = qt.QComboBox()
        roleLabel = qt.QLabel("Role:")
        roleLabel.setToolTip("What role the profile should be marked as having.")

        # Add the roles already available to the combobox
        roleComboBox.addItems(self.master_config.profile_roles)

        # Make the combo-box editable
        roleComboBox.setEditable(True)

        self.roleComboBox = roleComboBox

        # Add it to our GUI layout
        layout.addRow(roleLabel, roleComboBox)

        # Add the blank-state checkbox
        blankStateBox = qt.QCheckBox()
        blankStateLabel = qt.QLabel("Reset to Default?")
        blankStateLabel.setToolTip("""
            If selected, the new profile will have no configuration settings, 
            being a "blank slate". If unchecked, the configuration settings of the 
            current profile (including the last-used settings) are copied over instead.
        """)
        self.blankSlateBox = blankStateBox
        layout.addRow(blankStateLabel, blankStateBox)

        # Add our button array to the bottom of the GUI
        self.buttonBox = self.addButtons()
        layout.addRow(self.buttonBox)

        # Only enable the "confirm" button when a valid username is present
        okButton = self.buttonBox.button(qt.QDialogButtonBox.Ok)
        def syncOkButtonState(profile_label: str):
            stripped_name = profile_label.strip()
            if not stripped_name:
                okButton.setEnabled(False)
                okButton.setToolTip("Profiles must have a non-blank label")
            elif stripped_name in self.master_config.profiles.keys():
                okButton.setEnabled(False)
                okButton.setToolTip("The provided profile already exists!")
            else:
                okButton.setEnabled(True)
                okButton.setToolTip("")
        self.profileLabelEdit.textChanged.connect(syncOkButtonState)
        # Sync the OK button's state immediately
        syncOkButtonState(profileLabelEdit.text)

    def onButtonPressed(self, button: qt.QPushButton):
        # Get the role of the button
        button_role = self.buttonBox.buttonRole(button)
        # Match it to our corresponding function
        # TODO: Replace this with a `match` statement when porting to Slicer 5.9
        if button_role == qt.QDialogButtonBox.AcceptRole:
            self.createNewProfile()
            self.accept()
        elif button_role == qt.QDialogButtonBox.RejectRole:
            self.reject()
        else:
            raise ValueError("Pressed a button with an invalid role somehow...")

    ## Access Management ##s
    @property
    def profile(self) -> str:
        return self.profileLabelEdit.text

    @property
    def selected_role(self) -> str:
        return self.roleComboBox.currentText.strip()

    @property
    def shouldBlankState(self) -> bool:
        return self.blankSlateBox.isChecked()

    ## Utils
    def createNewProfile(self):
        # Build the profile config dict from our GUI
        profile_dict = {
            ProfileConfig.ROLE_KEY: self.selected_role
        }

        # Add a new entry into the config file
        if self.shouldBlankState:
            self.master_config.new_profile(
                self.profile,
                profile_dict
            )
        else:
            self.master_config.new_profile(
                self.profile,
                profile_dict,
                self.reference_profile
            )

        # If the role is new, add it to the master config list
        if self.selected_role not in self.master_config.profile_roles:
            self.master_config.profile_roles.append(self.selected_role)


class ProfileConfigDialog(ConfigDialog[ProfileConfig]):
    """
    Configuration dialog which allows the user to configure a
    profile's CART settings.
    """

    def buildGUI(self, layout: qt.QFormLayout):
        # General window properties
        self.setWindowTitle("CART Configuration")

        # Build the widget for the Iterative Save attribute
        self._iterSaveWidget(layout)

        self._roleWidget(layout)

    def _iterSaveWidget(self, layout):
        # Add a checkbox for the state of autosaving
        iterSaveCheck = qt.QCheckBox()
        iterSaveLabel = qt.QLabel("Save on Iteration:")
        iterSaveLabel.setToolTip(
            "If checked, the Task will try to save when you change cases automatically."
        )

        # Synchronize to our bound config
        iterSaveCheck.setChecked(self.bound_config.save_on_iter)

        # Update the config's state when it changes
        def setSaveOnIter(new_state: bool):
            self.bound_config.save_on_iter = bool(new_state)
        iterSaveCheck.stateChanged.connect(setSaveOnIter)

        # Add it to our layout
        layout.addRow(iterSaveLabel, iterSaveCheck)
        # Track it for later synchronization
        self.iterSaveCheck = iterSaveCheck

    def _roleWidget(self, layout):
        # Add a combobox that lets the user select a profile's role
        roleComboBox = qt.QComboBox()
        roleLabel = qt.QLabel("Role:")
        roleLabel.setToolTip("What role the profile should be marked as having.")

        # Make the combo-box editable
        roleComboBox.setEditable(True)

        # Set the selected role to match the current profile's role
        roleComboBox.setCurrentText(self.bound_config.role)

        # When a new role is selected, update our backing dict
        def changeRole(new_role: str):
            self.bound_config.role = new_role
        roleComboBox.currentTextChanged.connect(changeRole)

        # Add it to our layout
        layout.addRow(roleLabel, roleComboBox)
        # Track it for later synchronization
        self.roleComboBox = roleComboBox

    def sync(self):
        # Iterative save checkbox
        self.iterSaveCheck.setChecked(self.bound_config.save_on_iter)

        # Role selection combobox
        self.roleComboBox.clear()
        self.roleComboBox.addItems(self.bound_config.valid_roles)
        self.roleComboBox.currentText = self.bound_config.role


# The location of the config file for this installation of CART.
MAIN_CONFIG = Path(__file__).parent.parent.parent / "configuration.json"

GLOBAL_CONFIG = CARTConfig(MAIN_CONFIG)
