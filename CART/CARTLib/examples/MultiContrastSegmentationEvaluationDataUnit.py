from pathlib import Path
from typing import Optional

import slicer
from ..core.DataUnitBase import DataUnitBase
from ..utils.data import load_segmentation, load_volume, create_subject
from slicer.i18n import tr as _


class MultiContrastSegmentationEvaluationDataUnit(DataUnitBase):
    """
    DataUnit for segmentation evaluation supporting any number of volumes.
    Dynamically discovers all case_data keys containing "volume", loads them,
    and uses one as the primary for geometry alignment.
    """

    SEGMENTATION_KEY = "segmentation"
    COMPLETED_KEY = "completed"

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: Optional[slicer.vtkMRMLScene] = slicer.mrmlScene,
    ):
        super().__init__(case_data, data_path, scene)

        # --- Discover all volume keys dynamically ---
        self.volume_keys = [k for k in self.case_data if "volume" in k.lower()]
        if not self.volume_keys:
            raise ValueError(f"No volume keys found in case_data for case {self.uid}")

        # Pick primary: one containing "primary", else first alphabetically
        self.primary_volume_key = next(
            (k for k in self.volume_keys if "primary" in k.lower()),
            self.volume_keys[0],
        )

        # Build paths for volumes and segmentation
        self.volume_paths: dict[str, Path] = {
            key: self.data_path / self.case_data[key] for key in self.volume_keys
        }
        self.segmentation_path: Path = (
            self.data_path / self.case_data[self.SEGMENTATION_KEY]
        )

        # Prepare storage for loaded nodes
        self.volume_nodes: dict[str, slicer.vtkMRMLScalarVolumeNode] = {}
        self.primary_volume_node: Optional[slicer.vtkMRMLScalarVolumeNode] = None
        self.segmentation_node: Optional[slicer.vtkMRMLSegmentationNode] = None

        # Slicer hierarchy for grouping nodes
        self.hierarchy_node = slicer.mrmlScene.GetSubjectHierarchyNode()
        self.subject_id: Optional[int] = None

        # Track completion state
        self.is_complete = case_data.get(self.COMPLETED_KEY, False)
        # Load our resources
        self._initialize_resources()

    def to_dict(self) -> dict[str, str]:
        """Serialize back to case_data format."""
        output = {key: self.case_data[key] for key in self.volume_keys}
        output[self.SEGMENTATION_KEY] = self.case_data[self.SEGMENTATION_KEY]
        output[self.COMPLETED_KEY] = self.is_complete
        return output

    def focus_gained(self) -> None:
        """Show all volumes and segmentation when this unit gains focus."""
        for node in self.volume_nodes.values():
            node.SetDisplayVisibility(True)
        self.segmentation_node.SetDisplayVisibility(True)
        self._set_subject_shown(True)

    def focus_lost(self) -> None:
        """Hide all volumes and segmentation when focus is lost."""
        for node in self.volume_nodes.values():
            node.SetDisplayVisibility(False)
        self.segmentation_node.SetDisplayVisibility(False)
        self._set_subject_shown(False)

    def clean(self) -> None:
        """Clean up the hierarchy node and its children."""
        super().clean()
        if self.subject_id is not None:
            self.hierarchy_node.RemoveItem(self.subject_id)

    def _validate(self) -> None:
        """
        Ensure that all discovered volume keys and the segmentation key
        refer to existing files.
        """
        for key in self.volume_keys:
            self.validate_key_is_file(key)
        self.validate_key_is_file(self.SEGMENTATION_KEY)

    def validate_key_is_file(self, key: str) -> None:
        """
        Confirm that case_data[key] exists, is a path under data_path,
        and refers to a file.
        """
        rel_path = self.case_data.get(key)
        if not rel_path:
            raise ValueError(f"Case {self.uid} missing required entry '{key}'.")
        full_path = self.data_path / rel_path
        if not full_path.exists():
            raise ValueError(f"Path for '{key}' does not exist: {full_path}")
        if not full_path.is_file():
            raise ValueError(f"Path for '{key}' is not a file: {full_path}")

    def _initialize_resources(self) -> None:
        """
        Load all volumes and the segmentation into MRML nodes,
        sync geometry, and create a subject hierarchy.
        """
        primary_node = self._init_volume_nodes()
        seg_node = self._init_segmentation_node()

        # Align segmentation to primary volume geometry
        seg_node.SetReferenceImageGeometryParameterFromVolumeNode(primary_node)

        # Group in subject hierarchy
        self.subject_id = create_subject(
            self.uid, self.segmentation_node, *self.volume_nodes.values()
        )

    def _init_volume_nodes(self) -> slicer.vtkMRMLScalarVolumeNode:
        """
        Load each volume path into a volume node, name it,
        store in resources, and identify the primary.
        """
        for key in self.volume_keys:
            path = self.volume_paths[key]
            node = load_volume(path)
            node.SetName(f"{self.uid}_{key}")
            self.volume_nodes[key] = node
            self.resources[key] = node
            if key == self.primary_volume_key:
                self.primary_volume_node = node
        return self.primary_volume_node  # primary

    def _init_segmentation_node(self) -> slicer.vtkMRMLSegmentationNode:
        """
        Load the segmentation file into a segmentation node,
        name it, and store in resources.
        """
        self.segmentation_node = load_segmentation(self.segmentation_path)
        self.segmentation_node.SetName(f"{self.uid}_{self.SEGMENTATION_KEY}")
        self.resources[self.SEGMENTATION_KEY] = self.segmentation_node
        return self.segmentation_node

    def _set_subject_shown(self, new_state: bool) -> None:
        """
        Expand or collapse the subject hierarchy group.
        """
        if self.subject_id is not None:
            self.hierarchy_node.SetItemExpanded(self.subject_id, new_state)
            self.hierarchy_node.SetItemDisplayVisibility(self.subject_id, new_state)
