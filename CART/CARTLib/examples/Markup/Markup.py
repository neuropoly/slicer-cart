from typing import Optional

import qt

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory, D
from CARTLib.utils.config import ProfileConfig, DictBackedConfig
from CARTLib.utils.data import CARTStandardUnit
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import CARTMarkupEditorWidget


@cart_task("Markup")
class MarkupTask(TaskBaseClass[CARTStandardUnit]):
    def __init__(self, profile: ProfileConfig):
        super().__init__(profile)

        # GUI and data unit
        self.gui: Optional[MarkupGUI] = None
        self.data_unit: Optional[CARTStandardUnit] = None

        # Markup tracking
        self.markups: list[tuple[str, Optional[str]]] = []
        self.untracked_markups: dict[str, list[str]] = {}

        # Output logging
        self._output_manager: Optional[MarkupOutput] = None

        # Config management
        self.config: MarkupConfig = MarkupConfig(parent_config=self.profile)

    def setup(self, container: qt.QWidget):
        # Initialize the GUI
        self.gui = MarkupGUI(self)
        container.setLayout(self.gui.setup())

        # If we have a data unit, notify the GUI to synchronize
        if self.data_unit:
            self.gui.sync()

    def receive(self, data_unit: D):
        # Update the data unit
        self.data_unit = data_unit

        # If we have a GUI, sync it
        if self.gui:
            self.gui.sync()

    def save(self) -> Optional[str]:
        pass

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": CARTStandardUnit
        }


class MarkupGUI:
    def __init__(self, bound_task: MarkupTask):
        self.bound_task = bound_task

        # Widget displaying the data unit
        self.markupEditor: CARTMarkupEditorWidget = CARTMarkupEditorWidget()

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout
        layout = qt.QFormLayout()

        # Insert the markup editor widget
        layout.addWidget(self.markupEditor)

        # Return the result
        return layout

    def sync(self):
        self.markupEditor.refresh()

    @property
    def data_unit(self) -> CARTStandardUnit:
        return self.bound_task.data_unit


class MarkupOutput:
    def __init__(self):
        pass


class MarkupConfig(DictBackedConfig):
    CONFIG_KEY = "markup"

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    def show_gui(self) -> None:
        pass
