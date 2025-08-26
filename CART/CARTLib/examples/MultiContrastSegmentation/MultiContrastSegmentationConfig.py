import qt

from CARTLib.utils.config import DictBackedConfig, ConfigDialog, UserConfig


class MultiContrastSegmentationConfig(DictBackedConfig):
    """
    Configuration manager for the MultiContrast task
    """
    CONFIG_KEY = "multi_contrast_segmentation"

    def __init__(self, parent_config: UserConfig):
        super().__init__(parent_config=parent_config)

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## Configuration Options ##
    SHOW_ON_LOAD_KEY = "show_on_load"

    @property
    def show_on_load(self) -> bool:
        return self._backing_dict.get(self.SHOW_ON_LOAD_KEY, True)

    @show_on_load.setter
    def show_on_load(self, new_state: bool):
        self._backing_dict[self.SHOW_ON_LOAD_KEY] = new_state
        self.has_changed = True

    ## Utils ##
    def show_gui(self):
        # Build the Config prompt
        prompt = MultiContrastSegmentationConfigGUI(bound_config=self)
        # Show it, blocking other interactions until its resolved
        prompt.exec()


class MultiContrastSegmentationConfigGUI(
    ConfigDialog[MultiContrastSegmentationConfig]
):
    """
    Configuration dialog which allows the user to configure this task.
    """
    def buildGUI(self, layout: qt.QFormLayout):
        # General window properties
        self.setWindowTitle("CART Configuration")

        # Add the load-on-show widget
        self._buildLoadOnShowCheckBox(layout)

    def _buildLoadOnShowCheckBox(self, layout):
        # Add a checkbox for "show_on_load"
        loadOnShowCheckBox = qt.QCheckBox()
        loadOnShowLabel = qt.QLabel("Show Segmentation on Load:")
        loadOnShowLabel.setToolTip(
            "If checked, the primary segmentation (if present) will be shown immediately."
        )

        # Ensure it is synchronized with the configuration settings
        def onLoadShowCheckBoxChanged(new_val: bool):
            self.bound_config.show_on_load = new_val
        loadOnShowCheckBox.stateChanged.connect(onLoadShowCheckBoxChanged)

        # Add it to our layout
        layout.addRow(loadOnShowLabel, loadOnShowCheckBox)

        # Track it for later
        self.loadOnShowCheckBox = loadOnShowCheckBox

    def sync(self):
        # Load-on-show checkbox synchronization
        self.loadOnShowCheckBox.setChecked(self.bound_config.show_on_load)
