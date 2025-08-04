from pathlib import Path
from typing import Optional
import itertools

import slicer
from CARTLib.core.DataUnitBase import DataUnitBase
from CARTLib.utils.data import (
    load_segmentation,
    load_volume,
    create_subject,
    load_markups,
    extract_case_keys_by_prefix,
    create_empty_segmentation_node,
    parse_volumes,
    parse_markups,
    parse_segmentations,
)
from CARTLib.utils.layout import LayoutHandler, Orientation


class MultiContrastSegmentationEvaluationDataUnit(DataUnitBase):
    """
    DataUnit for segmentation evaluation supporting any number of volumes.
    Dynamically discovers all case_data keys containing "volume", loads them,
    and uses one as the primary for geometry alignment.
    """

    DEFAULT_SEGMENTATION_KEY = "default_segmentation"
    COMPLETED_KEY = "completed"
    COMPLETED_BY_KEY = "completed_by"

    DEFAULT_ORIENTATION = Orientation.AXIAL

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,  # Scene is NOT optional.
        # Default scene is the global MRML scene, which is always available.
    ) -> None:
        super().__init__(case_data, data_path, scene)

        # Volume-related parameters
        self.primary_volume_key: str = ""

        self.volume_keys: list[str]
        self.volume_paths: dict[str, Path]
        self.primary_volume_key: str
        self.volume_keys, self.volume_paths, self.primary_volume_key = parse_volumes(
            case_data, data_path
        )
        self.volume_nodes: dict[str, slicer.vtkMRMLScalarVolumeNode] = dict()

        # Segmentation-related parameters
        self.segmentation_keys: list[str]
        self.segmentation_paths: dict[str, Path]
        self.primary_segmentation_key: str
        (
            self.segmentation_keys,
            self.segmentation_paths,
            self.primary_segmentation_key,
        ) = parse_segmentations(case_data, data_path)
        self.segmentation_nodes: dict[str, slicer.vtkMRMLSegmentationNode] = dict()
        self.primary_segmentation_node: Optional[slicer.vtkMRMLSegmentationNode] = None

        # Markup-related parameters
        self.markup_keys: list[str]
        self.markup_paths: dict[str, Path]
        self.markup_keys, self.markup_paths = parse_markups(case_data, data_path)
        self.markup_nodes: dict[str, slicer.vtkMRMLMarkupsFiducialNode] = dict()

        # Load everything into memory
        self._initialize_resources()

        # Create a subject associated with this data unit
        self.hierarchy_node = scene.GetSubjectHierarchyNode()
        self.subject_id = create_subject(
            self.uid,
            *self.segmentation_nodes.values(),
            *self.volume_nodes.values(),
            *self.markup_nodes.values(),
        )

        self.is_complete = case_data.get(self.COMPLETED_KEY, False)

        # Layout manager for this data unit; as it has MRML nodes, it needs to be
        # cleaned up on a per-unit basis.
        self.layout_handler: LayoutHandler = LayoutHandler(
            list(self.volume_nodes.values()),
            primary_volume_node=self.primary_volume_node,
            orientation=self.DEFAULT_ORIENTATION,
        )

    def get_primary_segmentation_path(self) -> Optional[Path]:
        """
        Get the file name for the primary segmentation output.
        If no primary segmentation key is set, return None.
        """
        if self.primary_segmentation_key is None:
            return None
        return self.segmentation_paths.get(self.primary_segmentation_key)

    def set_orientation(self, ori: Orientation):
        # Update our layout to match
        self.layout_handler.set_orientation(ori)

    def to_dict(self) -> dict[str, str]:
        """Serialize back to case_data format."""
        output = {key: self.case_data[key] for key in self.volume_keys}
        output.update({key: self.case_data[key] for key in self.segmentation_keys})
        output.update({key: self.case_data[key] for key in self.markup_keys})
        output[self.COMPLETED_KEY] = self.is_complete
        return output

    def focus_gained(self) -> None:
        """Show all volumes and segmentation when this unit gains focus."""
        # Reveal all the data nodes again
        for node in itertools.chain(
            self.volume_nodes.values(),
            self.segmentation_nodes.values(),
            self.markup_nodes.values(),
        ):
            node.SetDisplayVisibility(True)
            node.SetSelectable(True)
            node.SetHideFromEditors(False)

        self._set_subject_shown(True)

    def focus_lost(self) -> None:
        """Hide all volumes and segmentation when focus is lost."""
        for node in itertools.chain(
            self.volume_nodes.values(),
            self.segmentation_nodes.values(),
            self.markup_nodes.values(),
        ):
            node.SetDisplayVisibility(False)
            node.SetSelectable(False)
            node.SetHideFromEditors(True)

        self._set_subject_shown(False)

    def clean(self) -> None:
        """Clean up the hierarchy node and its children."""
        super().clean()

        # If we are bound to a subject, remove it from the scene
        if self.subject_id is not None:
            self.hierarchy_node.RemoveItem(self.subject_id)

        # Ensure the layout handler is cleaned up as well
        self.layout_handler.clean()

    def _validate(self) -> None:
        """
        Ensure that all discovered volume keys and the segmentation key
        refer to existing files.
        """
        for key in self.volume_keys:
            self.validate_key_is_file(key)
        for key in self.segmentation_keys:
            # Special case; a "default" segmentation is created if none are provided
            if key == self.DEFAULT_SEGMENTATION_KEY:
                continue
            if key is not None:
                self.validate_key_is_file(key)

    def validate_key_is_file(self, key: str) -> None:
        """
        Confirm that case_data[key] exists, is a path under data_path,
        and refers to a file.
        """
        rel_path = self.case_data.get(key)
        # If the path wasn't specified, we assume the user wants it skipped/created
        if not rel_path:
            return
        # If there was a path, ensure it exists and is a file
        full_path = self.data_path / rel_path
        if not full_path.exists():
            raise ValueError(f"Path for '{key}' does not exist: {full_path}")
        if not full_path.is_file():
            raise ValueError(f"Path for '{key}' is not a file: {full_path}")

    def _initialize_resources(self) -> None:
        """
        Load volume nodes and segmentation nodes, align geometry,
        and register under a single subject in the hierarchy.
        """
        self._init_volume_nodes()
        self._init_segmentation_nodes()
        self._init_markups_nodes()

    def _init_volume_nodes(self) -> None:
        """
        Load each volume path into a volume node, name it,
        store in resources, and identify the primary.
        """
        for key, path in self.volume_paths.items():
            # If the volume is blank, skip it
            if path is None:
                continue
            # Attempt to load the volume and track it
            node = load_volume(path)
            node.SetName(f"{self.uid}_{key}")
            self.volume_nodes[key] = node
            self.resources[key] = node

            # If this is our primary volume, track it outright for ease of reference
            if key == self.primary_volume_key:
                self.primary_volume_node = node

    def _init_segmentation_nodes(self) -> None:
        """
        For each segmentation key, load if file exists; otherwise create empty node.
        Then pick the primary segmentation.
        """
        # If we don't have a primary volume yet, this method was called too early
        if not self.primary_volume_node:
            raise ValueError(
                "Cannot initialize segmentation nodes prior to volume nodes!"
            )

        for i, key in enumerate(self.segmentation_keys):
            seg_path = self.segmentation_paths.get(key, None)
            if seg_path and seg_path.exists():
                node = load_segmentation(seg_path)
            elif key == self.primary_segmentation_key:
                # Assume the user always wants a segment associated w/ the primary key
                node = create_empty_segmentation_node(
                    f"{self.uid}_{key}",
                    reference_volume=self.primary_volume_node,
                    scene=self.scene,
                )
            else:
                # If neither of the above, skip
                continue

            node.SetName(f"{self.uid}_{key}")
            node.SetReferenceImageGeometryParameterFromVolumeNode(
                self.primary_volume_node
            )
            # Set the colors of each segmentation
            if key == self.primary_segmentation_key:
                node.GetDisplayNode().SetOpacity(1.0)
            else:
                # TODO This should be configurable and a button to toggle visibility of non primary segmentations
                display_node = node.GetDisplayNode()
                segmentIds = node.GetSegmentation().GetSegmentIDs()
                print(
                    f"Setting color for non-primary segmentation {key} with segments: {segmentIds}"
                )
                # TODO MAKE THIS COLOR SETTING A UTIL FUNCTION AND MORE CONFIGURABLE
                # display_node.SetOpacity(0.1)
                for i, segment_id in enumerate(segmentIds):
                    print(f"Setting color for segment {segment_id} in {key} ")
                    display_node.SetSegmentVisibility2DFill(segment_id, False)
                    display_node.SetSegmentVisibility2DOutline(segment_id, True)
                    segment = node.GetSegmentation().GetSegment(segment_id)
                    colors = slicer.util.getNode("GenericColors")
                    lookup_table = colors.GetLookupTable()
                    segment.SetColor(
                        # Trim the last element (alpha)
                        *lookup_table.GetTableValue(i + 2)[:-1]
                    )
                else:
                    print(
                        f"Warning: Display node for {key} is None. Skipping color setup."
                    )
            self.segmentation_nodes[key] = node
            self.resources[key] = node

        self.primary_segmentation_node = self.segmentation_nodes[
            self.primary_segmentation_key
        ]

    def _init_markups_nodes(self) -> None:
        """
        Load each markup path into a markups node, name it,
        store in resources, and identify the primary.
        """
        for key, path in self.markup_paths.items():
            # If the markup was blank, skip it
            if path is None:
                continue
            # Try to load all markups from the file
            nodes = load_markups(path)
            for i, node in enumerate(nodes):
                if not isinstance(node, slicer.vtkMRMLMarkupsFiducialNode):
                    raise TypeError(
                        f"Expected a MarkupsFiducialNode, got {type(node)} for key {key}"
                    )
                c_name = node.GetName()
                node.SetName(f"{self.uid}_{c_name}_{key}_{i}")
                self.markup_nodes[f"{key}_{i}"] = node
                self.resources[f"{key}_{i}"] = node

    def _set_subject_shown(self, new_state: bool) -> None:
        """
        Expand or collapse the subject hierarchy group.
        """
        if self.subject_id is not None:
            self.hierarchy_node.SetItemExpanded(self.subject_id, new_state)
            self.hierarchy_node.SetItemDisplayVisibility(self.subject_id, new_state)
