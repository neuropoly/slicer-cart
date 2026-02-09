from pathlib import Path
from typing import Optional

import qt
import slicer

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import showSuccessPrompt

from SegmentationReviewGUI import SegmentationReviewGUI
from SegmentationReviewOutputManager import SegmentationReviewOutputManager
from SegmentationReviewUnit import (
    SegmentationReviewUnit,
)
from SegmentationReviewConfig import SegmentationReviewConfig


@cart_task("Segmentation Review")
class SegmentationReviewTask(
    TaskBaseClass[SegmentationReviewUnit]
):
    README_PATH = Path(__file__).parent / "README.md"

    def __init__(self, master_profile: MasterProfileConfig, job_profile: JobProfileConfig):
        super().__init__(master_profile, job_profile)

        # Local Attributes
        self.gui: Optional[SegmentationReviewGUI] = None
        self.data_unit: Optional[SegmentationReviewUnit] = None
        self.segments_to_save: set[str] = set()

        # Configuration
        self.config: SegmentationReviewConfig = SegmentationReviewConfig(
            parent_config=self.job_profile
        )

        # Output manager
        self.output_manager = SegmentationReviewOutputManager(
            config=self.job_profile
        )

    @classmethod
    def description(cls):
        with open(cls.README_PATH, 'r') as fp:
            return fp.read()

    @property
    def output_dir(self) -> Optional[Path]:
        return self.job_profile.output_path

    @output_dir.setter
    def output_dir(self, new_dir: Path):
        self.job_profile.output_path = new_dir

    @property
    def csv_log_path(self) -> Optional[Path]:
        return self.output_manager.csv_log_path

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")

        # Initialize the GUI: this prompts the user to configure some attributes we need
        self.gui = SegmentationReviewGUI(self)
        layout = self.gui.setup()

        # Integrate the task's GUI into CART
        container.setLayout(layout)

        # If we have a data unit at this point, synchronize the GUI to it
        if self.data_unit:
            self.gui.update(self.data_unit)
        self.gui.enter()

    def receive(self, data_unit: SegmentationReviewUnit) -> None:
        # Track the data unit for later
        self.data_unit = data_unit

        # Display primary volume + segmentation overlay
        slicer.util.setSliceViewerLayers(
            background=data_unit.primary_volume_node,
            foreground=data_unit.primary_segmentation_node,
            fit=True,
        )

        # By default, all segmentations are saved
        for s in self.data_unit.segmentation_keys:
            if s not in self.segments_to_save:
                self.segments_to_save.add(s)

        # Hide the segmentation node if requested by the user's config
        self.data_unit.set_primary_segments_visible(
            self.config.show_on_load
        )

        # If we have GUI, update it as well
        if self.gui:
            self.gui.update(data_unit)

    def cleanup(self) -> None:
        # Break the cyclical link with our GUI so garbage collection can run
        self.gui = None

    def enter(self) -> None:
        if self.gui:
            self.gui.enter()

    def exit(self) -> None:
        if self.gui:
            self.gui.exit()

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """
        We currently only support one data unit type, so we only provide it to
         the user
        """
        return {"Segmentation": SegmentationReviewUnit}

    def can_save(self):
        # If we don't have a data unit or output manager, we can't even consider saving
        if not self.data_unit or not self.output_manager:
            return False
        # Otherwise, check with our output manager
        return self.output_manager.can_save(self.data_unit)

    def save(self) -> Optional[str]:
        """
        Save the current segmentation using the output manager.
        """
        # Confirm we can save before trying
        if len(self.segments_to_save) < 1:
            raise ValueError("No segmentations selected to save!")
        elif not self.data_unit:
            raise ValueError("Theres no loaded case! Cannot save.")
        elif not self.output_manager:
            raise ValueError("You managed to initialize the task without an output handler. "
                             "Cannot save; please report this to the developers.")
        # Get the output manager to try and save the result
        msg = self.output_manager.save_unit(self.data_unit, self.segments_to_save)
        showSuccessPrompt(msg)

    def isTaskComplete(self, case_data: dict[str, str]) -> bool:
        # The user might not have selected an output directory
        if not self.output_manager:
            # Without an output specified, we can't determine if we're done or not
            return False

        # Delegate to the output manager
        return self.output_manager.is_case_completed(case_data)

    @classmethod
    def feature_types(cls, data_factory_label: str) -> dict[str, str]:
        # Defer to the data unit itself
        duf = cls.getDataUnitFactories().get(data_factory_label, None)
        if duf == SegmentationReviewUnit:
            return SegmentationReviewUnit.feature_types()
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
        if duf is SegmentationReviewUnit:
            return SegmentationReviewUnit.feature_label_for(
                initial_label, feature_type
            )
        return initial_label
