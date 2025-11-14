from functools import cached_property
from pathlib import Path
from typing import Optional

import qt
import ctk

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.examples.GenericClassification.GenericClassificationOutputManager import GenericClassificationOutputManager
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import showSuccessPrompt

from GenericClassificationGUI import GenericClassificationGUI
from GenericClassificationUnit import GenericClassificationUnit


@cart_task("Generic Classification")
class GenericClassificationTask(TaskBaseClass[GenericClassificationUnit]):
    """
    Task for classifying cases.

    Can be run in two modes:
    * Single Class: Only one classification can be selected per case
    * Multi-class: Multiple classifications can be selected per case

    Saves the classification(s) into a CSV folder
    """
    def __init__(self, profile: ProfileConfig):
        super().__init__(profile)

        # Track the active GUI instance, if any
        self.gui: Optional[GenericClassificationGUI] = None

        # CSV Log (path + contents)
        self.output_path: Optional[Path] = None

        # Currently managed data unit
        self.current_unit: Optional[GenericClassificationUnit] = None

        # Currently registered classes, including their description
        self.class_map: dict[str, str] = dict()

        # The output manager for this class
        self._output_manager: Optional[GenericClassificationOutputManager] = None

    @property
    def classes(self) -> list[str]:
        return list(self.class_map.keys())

    @cached_property
    def output_manager(self):
        return GenericClassificationOutputManager(
            self.profile, self.output_path
        )

    def setup(self, container: qt.QWidget):
        # Prompt for an output path
        self.output_path = self._promptForOutput()
        if not self.output_path:
            raise ValueError("No output path provided, terminating.")

        # Try to retrieve the last-used class map from the metadata
        self.class_map = self.output_manager.read_metadata()

        # Create and track the GUI
        self.gui = GenericClassificationGUI(self)
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

    def _promptForOutput(self):
        """
        Prompt the user to provide an output path
        """
        prompt = qt.QDialog()
        prompt.setWindowTitle("Select Output Path")

        # Create a layout for the dialog
        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        # Instruction label
        instructionLabel = qt.QLabel(
            "Specify where this task should save its results:"
        )
        instructionLabel.setWordWrap(True)
        layout.addWidget(instructionLabel)

        # Add a path-line edit button, forcing it to select only directories
        pathLineEdit = ctk.ctkPathLineEdit()
        pathLineEdit.setToolTip(
            "Specify file path for classification results."
        )
        pathLineEdit.filters = ctk.ctkPathLineEdit.Dirs
        layout.addWidget(pathLineEdit)

        # Add a "confirm" button
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok
        )
        def onClick(_):
            # If not path has been provided, encourage the user to select one
            if pathLineEdit.currentPath.strip() is "":
                msg = qt.QMessageBox()
                msg.setWindowTitle("Missing Path")
                msg.setText("Please provide a valid output path.")
                msg.setStandardButtons(
                    qt.QMessageBox.Ok
                )
                msg.exec()
            else:
                prompt.accept()
        buttonBox.clicked.connect(onClick)
        layout.addWidget(buttonBox)

        # Make the prompt a bit wider
        prompt.resize(300, prompt.minimumHeight)

        # Show the prompt
        result = prompt.exec()

        # If the result is an "accept" signal, try to return the resulting path
        if result:
            return Path(pathLineEdit.currentPath)

        # Otherwise, return none
        return None

    def receive(self, data_unit: GenericClassificationUnit):
        # Track the data unit for later
        self.current_unit = data_unit

        # Refresh the GUI to match the new data unit's contents
        if self.gui:
            self.gui.syncWithDataUnit()

    def save(self) -> Optional[str]:
        # Attempt to save the data unit + current metadata
        result_msg = self.output_manager.save_unit(self.current_unit)

        self.output_manager.save_metadata(self.class_map)

        # If we have a GUI, show the result to the user
        if self.gui and result_msg:
            showSuccessPrompt(result_msg)

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": GenericClassificationUnit
        }
