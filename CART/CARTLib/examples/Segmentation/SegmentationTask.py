import traceback
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qt

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.config import MasterProfileConfig, JobProfileConfig
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import showErrorPrompt

from SegmentationConfig import SegmentationConfig
from SegmentationGUI import SegmentationGUI
from SegmentationIO import SegmentationIO
from SegmentationUnit import SegmentationUnit


if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


@cart_task("Segmentation")
class SegmentationTask(
    TaskBaseClass[SegmentationUnit]
):

    README_PATH = Path(__file__).parent / "README.md"

    @classmethod
    def description(cls) -> str:
        with open(cls.README_PATH, "r") as fp:
            return fp.read()

        # TODO: Remove un-usable images

    @classmethod
    def feature_types(cls, data_factory_label: str) -> dict[str, str]:
        # Delegate to the data unit's defaults
        return SegmentationUnit.feature_types()

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
        if duf is SegmentationUnit:
            return SegmentationUnit.feature_label_for(initial_label, feature_type)
        return initial_label

    def __init__(
        self,
        master_profile: MasterProfileConfig,
        job_profile: JobProfileConfig,
        cohort_features: list[str],
    ):
        super().__init__(master_profile, job_profile, cohort_features)

        # Local Attributes
        self.gui: Optional[SegmentationGUI] = None
        self._data_unit: Optional[SegmentationUnit] = None

        # "Segmentation" features
        self.segmentation_features = [
            f for f in self.cohort_features if "segmentation" in f.lower()
        ]

        # Config init
        self.local_config = SegmentationConfig(job_profile)

        # I/O Manager
        self.io = SegmentationIO(master_profile, job_profile, self.local_config)

    @property
    def data_unit(self) -> SegmentationUnit:
        # Get-only; use "receive" instead
        return self._data_unit

    def setup(self, container: qt.QWidget):
        """
        Build the GUI's contents, returning the resulting layout for use.
        """
        self.logger.info("Setting up Segmentation Task!")

        # Initialize the layout we'll insert everything into
        self.gui = SegmentationGUI(self)
        container.setLayout(self.gui.setup())
        self.gui.enter()

        self.logger.info("Segmentation Task set up successfully!")

    def receive(self, data_unit: SegmentationUnit):
        self._data_unit = data_unit

        # Change the interpolation settings to match current setting
        self.apply_interp()

        # Ensure all segments are visible
        self.show_all_segments()

        # Hide "to-be-edited" segments, if requested
        if self.hide_editable_on_start:
            self.hide_editable_segments()

        # Add any custom segmentations configured by the user to the unit
        self._init_custom_segmentations()

        # If we have a GUI, refresh it
        if self.gui:
            self.gui.refresh()

    def save(self) -> Optional[str]:
        if not self.data_unit:
            self.logger.error("Could not save, no data unit has been loaded!")
        result_packet = self.io.save_unit(self.data_unit)
        # If we have an active GUI, prompt the user with the details
        if self.gui:
            self.gui.onSavePrompt(*result_packet)

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": SegmentationUnit
        }

    ## Configurable Settings ##
    @property
    def should_interpolate(self):
        return self.local_config.should_interpolate

    @should_interpolate.setter
    def should_interpolate(self, new_val: bool):
        self.local_config.should_interpolate = new_val
        self.local_config.save()

    def apply_interp(self):
        # Apply interpolation settings to the volume
        if not self.data_unit:
            return
        for n in self.data_unit.volume_nodes.values():
            display_node = n.GetDisplayNode()
            display_node.SetInterpolate(self.should_interpolate)

    @property
    def hide_editable_on_start(self) -> bool:
        return self.local_config.hide_editable_on_start

    @hide_editable_on_start.setter
    def hide_editable_on_start(self, new_val: bool):
        self.local_config.hide_editable_on_start = new_val
        self.local_config.save()

    def show_all_segments(self):
        if not self.data_unit:
            return
        for segment_node in self.data_unit.segmentation_nodes.values():
            display_node = segment_node.GetDisplayNode()
            display_node.SetAllSegmentsVisibility(True)

    def hide_editable_segments(self):
        if not self.data_unit:
            return
        for k in self.segmentations_to_save:
            segment_node = self.data_unit.segmentation_nodes.get(k)
            if not segment_node:
                print(f"No segment node for {k}")
                continue
            display_node = segment_node.GetDisplayNode()
            display_node.SetAllSegmentsVisibility(False)

    @property
    def save_blank_segments(self) -> bool:
        return self.local_config.save_blank_segmentations

    @save_blank_segments.setter
    def save_blank_segments(self, new_val: bool):
        self.local_config.save_blank_segmentations = new_val
        self.local_config.save()

    @property
    def custom_segmentations(self) -> dict[str, dict]:
        return self.local_config.custom_segmentations

    def new_custom_segmentation(self, new_name: str, output_str: str, color_hex: str):
        """
        Register a new custom segmentation. Adds a (blank) segmentation
        with the corresponding name to the current data unit as well.

        :param new_name: The name the segmentation should have
        :param output_str: The output path, pre-contextual formatting
        :param color_hex: The color the segmentation should be, in hex format
        """

        # Add it to our configuration
        self.local_config.add_custom_segmentation(new_name, output_str, color_hex)
        self.local_config.save()

        # If this is a new custom segmentation for the data unit, add it as well
        if self.data_unit and new_name not in self.data_unit.custom_segmentations.keys():
            try:
                # Generate the new node
                new_node = self.data_unit.add_custom_segmentation(new_name, color_hex)

                # If we have a GUI, update it
                if self.gui:
                    self.gui.refresh()
                    self.gui.selectSegmentationNode(new_node)
            except Exception as e:
                self.logger.error(traceback.format_exc())
                if self.gui:
                    showErrorPrompt(str(e), None)

    @property
    def segmentations_to_save(self) -> list[str]:
        return self.local_config.segmentations_to_save

    @segmentations_to_save.setter
    def segmentations_to_save(self, new_segs: list[str]):
        self.local_config.segmentations_to_save = new_segs
        self.local_config.save()

    @property
    def edit_output_path(self) -> str:
        return self.local_config.edit_output_path

    @edit_output_path.setter
    def edit_output_path(self, new_val: str):
        self.local_config.edit_output_path = new_val
        self.local_config.save()

    @property
    def default_custom_output_path(self) -> str:
        return self.local_config.default_custom_output_path

    @default_custom_output_path.setter
    def default_custom_output_path(self, new_val: str):
        self.local_config.default_custom_output_path = new_val
        self.local_config.save()

    ## Segmentation Management ##
    def _init_custom_segmentations(self):
        """
        Add a custom segmentation to the data unit
        """
        # If we don't have a data unit, end here w/ an error
        if not self.data_unit:
            msg = "Cannot add custom segmentation; no data unit has been loaded!"
            self.logger.error(msg)
            if self.gui:
                showErrorPrompt(msg, None)

        # Add each custom segmentation in turn
        for name, sub_vals in self.custom_segmentations.items():
            try:
                color_hex = sub_vals.get(self.local_config.CUSTOM_SEG_COLOR_KEY)
                self.data_unit.add_custom_segmentation(name, color_hex)
                if self.gui:
                    self.gui.refresh()
            # Skip duplicate key errors in this case
            except ValueError as e:
                if "already exists" in str(e):
                    continue
                raise e
            # All other errors should end the loop and notify the user
            except Exception as e:
                self.logger.error(traceback.format_exc())
                if self.gui:
                    showErrorPrompt(str(e), None)
                return

    def enter(self):
        if self.gui:
            self.gui.enter()

    def exit(self):
        if self.gui:
            self.gui.exit()

    def cleanup(self):
        # Break the cycling link
        self.gui = None
