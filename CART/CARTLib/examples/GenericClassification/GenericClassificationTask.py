from functools import cached_property
from pathlib import Path
from typing import Optional

import qt
import ctk

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.examples.GenericClassification.GenericClassificationOutputManager import GenericClassificationOutputManager
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
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
    README_PATH = Path(__file__).parent / "README.md"

    def __init__(
        self,
        master_profile: MasterProfileConfig,
        job_profile: JobProfileConfig,
        cohort_features: list[str],
    ):
        super().__init__(master_profile, job_profile, cohort_features)

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

    @classmethod
    def description(cls):
        with open(cls.README_PATH, 'r') as fp:
            return fp.read()

    @property
    def classes(self) -> list[str]:
        return list(self.class_map.keys())

    @cached_property
    def output_manager(self):
        return GenericClassificationOutputManager(self.job_profile)

    def setup(self, container: qt.QWidget):
        # Try to retrieve the last-used class map from the metadata
        self.class_map = self.output_manager.read_metadata()

        # Create and track the GUI
        self.gui = GenericClassificationGUI(self)
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

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

    @classmethod
    def feature_types(cls, data_factory_label: str) -> dict[str, str]:
        # Defer to the data unit itself
        duf = cls.getDataUnitFactories().get(data_factory_label, None)
        if duf == GenericClassificationUnit:
            return GenericClassificationUnit.feature_types()
        return {}

    @classmethod
    def format_feature_label_for_type(
        cls, initial_label: str, data_unit_factory_type: str, feature_type: str
    ):
        # Apply default comma processing
        initial_label = super().format_feature_label_for_type(
            initial_label, data_unit_factory_type, feature_type
        )
        # Defer to the data unit itself for further processing
        duf = cls.getDataUnitFactories().get(data_unit_factory_type, None)
        if duf is GenericClassificationUnit:
            return GenericClassificationUnit.feature_label_for(initial_label, feature_type)
        return initial_label
