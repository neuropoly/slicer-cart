from pathlib import Path
from typing import Optional

import slicer
from ..core.DataUnitBase import DataUnitBase
from ..utils.data import load_segmentation, load_volume, create_subject
from slicer.i18n import tr as _


class SegmentationEvaluationDataUnit(DataUnitBase):
    ## CASE_KEYS ##
    VOLUME_KEY = "volume"
    SEGMENTATION_KEY = "segmentation"
    COMPLETED_KEY = "completed"

    def __init__(
            self,
            case_data: dict[str, str],
            data_path: Path,
            scene: Optional[slicer.vtkMRMLScene] = slicer.mrmlScene
    ):
        super().__init__(case_data, data_path, scene)

        # Track the volume and segmentation nodes
        self.volume_node = None
        self.segmentation_node = None

        # Hierarchy node which manages subjects, for ease of access
        self.hierarchy_node = slicer.mrmlScene.GetSubjectHierarchyNode()

        # Subject ID for nodes associated with this data unit
        self.subject_id: int = None

        # Track whether this node has been processed already or not
        self.is_complete = case_data.get(self.COMPLETED_KEY, False)

        # Path to the original files; used for re-loading and sidecar fetching
        self.volume_path = self.data_path / self.case_data[self.VOLUME_KEY]
        self.segmentation_path = self.data_path / self.case_data[self.SEGMENTATION_KEY]

        # Initialize our resources
        self._initialize_resources()

    def to_dict(self) -> dict:
        return {
            self.VOLUME_KEY: self.case_data[self.VOLUME_KEY],
            self.SEGMENTATION_KEY: self.case_data[self.SEGMENTATION_KEY],
            self.COMPLETED_KEY: self.is_complete
        }

    def focus_gained(self):
        # Make our managed nodes visible again
        self.volume_node.SetDisplayVisibility(True)
        self.segmentation_node.SetDisplayVisibility(True)

        # Expand the subject hierarchy and make it visible
        self._set_subject_shown(True)

    def focus_lost(self):
        # Make our managed nodes hidden again
        self.volume_node.SetDisplayVisibility(False)
        self.segmentation_node.SetDisplayVisibility(False)

        # Collapse the subject hierarchy and hide it
        # KO: This works ~99% of the time, but randomly fails sometimes.
        #  No idea why...
        self._set_subject_shown(False)

    def clean(self):
        # Un-focus the contents first, avoiding some potential UI bugs
        super().clean()
        # Remove the subject (and, by extension, all its children)
        self.hierarchy_node.RemoveItem(self.subject_id)

    def _validate(self):
        # Confirm that both a "volume" and "segmentation" entry exit
        self.validate_key_is_file(self.VOLUME_KEY)
        self.validate_key_is_file(self.SEGMENTATION_KEY)

        self.validated = True

    def validate_key_is_file(self, key: str):
        """
        Validate a file we need designed by our case:
          * Has been designated in the case
          * Exists
          * Is a valid file
        """
        # Check that there is an entry matching this key in the case
        file_path = self.case_data.get(key, None)
        if not file_path:
            raise ValueError(
                f"Case {self.uid} was missing required entry '{key}'."
            )

        # Confirm that something matching the designated path exists on our drive
        file_path = self.data_path / file_path
        if not file_path.exists():
            raise ValueError(
                f"Path for '{key}' does not exist for case {self.uid}."
            )

        # Confirm that it is a file
        if not file_path.is_file():
            raise ValueError(
                f"Path for '{key}' for case {self.uid} was not a file."
            )

    def _initialize_resources(self):
        """
        Attempt to load the volume and segmentation files into memory as
         MRML nodes.
        """
        if not self.validated:
            raise ValueError(_("Data must be validated before initializing resources."))

        # Initialize the nodes containing our actual data
        vn = self._init_volume_node()
        sn = self._init_segmentation_node()

        # Ensure the segmentation node aligns with the geometry of the volume
        self.segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(
            self.volume_node
        )

        # Initialize a subject to hold everything in for management sakes
        self.subject_id = create_subject(self.uid, vn, sn)

    def _init_volume_node(self):
        # Load the volume node first
        self.volume_node = load_volume(self.volume_path)

        # Update it and add it to our resources for easy access elsewhere
        self.volume_node.SetName(f"{self.uid}_{self.VOLUME_KEY}")
        self.resources[self.VOLUME_KEY] = self.volume_node

        return self.volume_node

    def _init_segmentation_node(self):
        # Load the segmentation node
        self.segmentation_node = load_segmentation(self.segmentation_path)

        # Update it and add it to our resources for easy access elsewhere
        self.segmentation_node.SetName(f"{self.uid}_{self.SEGMENTATION_KEY}")
        self.resources[self.VOLUME_KEY] = self.volume_node

        return self.segmentation_node

    def _set_subject_shown(self, new_state: bool):
        self.hierarchy_node.SetItemExpanded(self.subject_id, new_state)
        self.hierarchy_node.SetItemDisplayVisibility(self.subject_id, new_state)
