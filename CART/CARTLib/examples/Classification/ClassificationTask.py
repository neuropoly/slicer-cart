from functools import cached_property
from pathlib import Path
from typing import Optional

import qt

from CARTLib.core.TaskBaseClass import TaskBaseClass
from CARTLib.core.DataUnitBase import DataUnitFactory
from CARTLib.examples.Classification.ClassificationConfig import ClassificationConfig
from CARTLib.examples.Classification.ClassificationOutputManager import ClassificationOutputManager
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import showSuccessPrompt

from ClassificationGUI import ClassificationGUI
from ClassificationUnit import ClassificationUnit


@cart_task("Classification")
class ClassificationTask(TaskBaseClass[ClassificationUnit]):
    """
    Task for classifying cases.

    Can be run in two modes:
    * Single Class: Only one classification can be selected per case
    * Multi-class: Multiple classifications can be selected per case

    Saves the classification(s) into a CSV folder
    """
    README_PATH = Path(__file__).parent / "README.md"

    def __init__(
        self,
        master_profile: MasterProfileConfig,
        job_profile: JobProfileConfig,
        cohort_features: list[str],
    ):
        super().__init__(master_profile, job_profile, cohort_features)

        # Track the active GUI instance, if any
        self.gui: Optional[ClassificationGUI] = None

        # CSV Log (path + contents)
        self.output_path: Optional[Path] = None

        # Currently managed data unit
        self.current_unit: Optional[ClassificationUnit] = None

        # Currently registered classes, including their description
        self.class_map: dict[str, str] = dict()

        # The output manager for this class
        self._output_manager: Optional[ClassificationOutputManager] = None

    @classmethod
    def description(cls):
        with open(cls.README_PATH, 'r') as fp:
            return fp.read()

    @property
    def classes(self) -> list[str]:
        return list(self.class_map.keys())

    @cached_property
    def output_manager(self):
        return ClassificationOutputManager(self.job_profile)

    def setup(self, container: qt.QWidget):
        # Try to retrieve the last-used class map from the metadata
        self.class_map = self.output_manager.read_metadata()

        # Create and track the GUI
        self.gui = ClassificationGUI(self)
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

    def receive(self, data_unit: ClassificationUnit):
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
    def init_config(cls, job_config: JobProfileConfig) -> ClassificationConfig:
        return ClassificationConfig(job_config)

    @classmethod
    def getDataUnitFactory(cls) -> DataUnitFactory:
        return ClassificationUnit
