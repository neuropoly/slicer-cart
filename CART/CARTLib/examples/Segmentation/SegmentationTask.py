from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qt

from CARTLib.core.TaskBaseClass import CARTTask
from CARTLib.core.DataUnitBase import DataUnitFactory
from CARTLib.utils.config import MasterProfileConfig, JobProfileConfig
from CARTLib.utils.data import VolumeResource, ReferenceVolumeResource
from CARTLib.utils.task import cart_task

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
    CARTTask[SegmentationUnit]
):

    README_PATH = Path(__file__).parent / "README.md"

    @classmethod
    def description(cls) -> str:
        with open(cls.README_PATH, "r") as fp:
            return fp.read()

        # TODO: Remove un-usable images

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

        # Self-managed configuration instance
        self.local_config = self.init_config(job_profile)

        # I/O Manager
        self.io = SegmentationIO(master_profile, job_profile, self.local_config)

    @property
    def data_unit(self) -> SegmentationUnit:
        # Get-only; use "receive" instead
        return self._data_unit

    @classmethod
    def getDataUnitFactory(cls) -> DataUnitFactory:
        return SegmentationUnit

    ## Configurable Settings ##
    @classmethod
    def init_config(cls, job_config: JobProfileConfig) -> SegmentationConfig:
        return SegmentationConfig(job_config)

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

    @property
    def save_blank_segments(self) -> bool:
        return self.local_config.save_blank_segmentations

    @save_blank_segments.setter
    def save_blank_segments(self, new_val: bool):
        self.local_config.save_blank_segmentations = new_val
        self.local_config.save()

    ## State Management ##
    def _find_reference_volume_path(self, case_data: dict):
        # Identify the reference volume path for this case
        reference_path = None
        for k, v in case_data.items():
            # Skip blanks; they're not valid
            if v is None or v == "":
                continue
            # Skip over non-volume entries as well
            if not VolumeResource.is_type(k):
                continue
            # Skip over paths which don't exist
            p = Path(v)
            if not p.is_absolute():
                p = self.job_profile.data_path / p
            if not p.exists():
                continue
            # Track the first valid volume we found as a fallback
            if reference_path is None:
                reference_path = p
            # If this is a valid reference volume, end here
            if ReferenceVolumeResource.is_type(k):
                reference_path = p
                break

        return reference_path

    def isTaskComplete(self, case_data: dict[str, str]) -> bool:
        # Ensure there's a valid UI
        uid = case_data.get("uid", None)
        if uid is None:
            return False

        # Identify the reference volume path for this case
        reference_path = self._find_reference_volume_path(case_data)

        # If there isn't one, assume the case is not complete
        if reference_path is None:
            return False

        # Delegate to our IO manager
        return self.io.is_case_done(uid, reference_path)

    def save(self) -> Optional[str]:
        # Try to save the data unit
        if not self.data_unit:
            self.logger.error("Could not save, no data unit has been loaded!")
        self.io.save_unit(self.data_unit)

    def generate_prior_data_for(self, case_data: dict) -> Optional[dict]:
        # Ensure there's a valid UI
        uid = case_data.get("uid", None)
        if uid is None:
            return None

        # Find the reference volume for this case
        reference_path = self._find_reference_volume_path(case_data)
        if reference_path is None:
            return None

        # Delegate to our IO instance
        return self.io.get_saved_segmentation_paths(uid, reference_path)

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

        # Apply our configuration options to the data unit
        data_unit.apply_segmentation_configs(self.local_config)

        # Change the interpolation settings to match current setting
        self.apply_interp()

        # Ensure all segments are visible
        self.show_all_segments()

        # Hide segments the user requested be hidden on load
        # TODO

        # If we have a GUI, refresh it
        if self.gui:
            self.gui.refresh()

    def enter(self):
        if self.gui:
            self.gui.enter()

    def exit(self):
        if self.gui:
            self.gui.exit()

    def cleanup(self):
        # Break the cycling link
        self.gui = None
