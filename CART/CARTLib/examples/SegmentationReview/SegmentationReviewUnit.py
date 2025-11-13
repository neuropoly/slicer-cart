from pathlib import Path
from typing import Optional

import slicer

from CARTLib.utils.data import create_empty_segmentation_node, CARTStandardUnit


class SegmentationReviewUnit(CARTStandardUnit):
    """
    DataUnit for segmentation evaluation supporting any number of volumes.
    Dynamically discovers all case_data keys containing "volume", loads them,
    and uses one as the primary for geometry alignment.
    """

    DEFAULT_SEGMENTATION_KEY = "default_segmentation"

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ) -> None:
        super().__init__(case_data, data_path, scene)

        # The "primary" segmentation is the one the user can edit
        self.primary_segmentation_key = self._identify_primary_segmentation()
        self.primary_segmentation_node: Optional[slicer.vtkMRMLSegmentationNode] = (
            self._init_primary_segmentation()
        )

        # Ensure the primary segmentation stands out
        self._update_segment_visuals()

    def _identify_primary_segmentation(self) -> str:
        # Find the first key labelled "primary", if it exists
        primary_segmentation_key = next(
            (k for k in self.segmentation_keys if "primary" in k.lower()),
            None,
        )
        if primary_segmentation_key:
            return primary_segmentation_key

        # Otherwise, select the first segmentation column instead
        if not len(self.segmentation_keys) < 1:
            return self.segmentation_keys[0]

        # If all the above failed, return the default key
        return self.DEFAULT_SEGMENTATION_KEY

    def _init_primary_segmentation(self):
        # Try to get a node associated with our primary key
        primary_node = self.segmentation_nodes.get(self.primary_segmentation_key, None)

        # If we don't have a primary node, create one
        if not primary_node:
            # The node itself
            primary_node = create_empty_segmentation_node(
                f"{self.uid}_{self.primary_segmentation_key}",
                reference_volume=self.primary_volume_node,
                scene=self.scene,
            )
            # Create a blank segment within the node that the user can edit
            primary_node.GetSegmentation().AddEmptySegment("", "blank")
            # Track it in our segmentation node map
            self.segmentation_nodes[self.primary_segmentation_key] = primary_node

        # Move the primary segmentation key to the front of the list;
        # this makes it auto-selected by most GUIs in Slicer and CART
        if self.primary_segmentation_key in self.segmentation_keys:
            self.segmentation_keys.remove(self.primary_segmentation_key)
        self.segmentation_keys = [self.primary_segmentation_key, *self.segmentation_keys]

        # Segmentation nodes only contains loaded nodes;
        # we need to skip over the keys w/o a corresponding node
        self.segmentation_nodes = {
            k: self.segmentation_nodes[k] for k in self.segmentation_keys
            if k in self.segmentation_nodes.keys()
        }

        # Return the node
        return primary_node

    def _update_segment_visuals(self):
        # Make all non-primary segmentation nodes an outline, emphasizing the primary node
        for label, node in self.segmentation_nodes.items():
            # Skip the primary segmentation key, leave it as-is
            if label == self.primary_segmentation_key:
                continue

            # TODO This should be configurable and a button to toggle visibility of non primary segmentations
            display_node = node.GetDisplayNode()
            if not display_node:
                print(
                    f"Warning: Display node for '{label}' is None. Cannot change display style."
                )
            segmentIds = node.GetSegmentation().GetSegmentIDs()
            # TODO MAKE THIS COLOR SETTING A UTIL FUNCTION AND MORE CONFIGURABLE
            # display_node.SetOpacity(0.1)
            for i, segment_id in enumerate(segmentIds):
                display_node.SetSegmentVisibility2DFill(segment_id, False)
                display_node.SetSegmentVisibility2DOutline(segment_id, True)

    def get_primary_segmentation_path(self) -> Optional[Path]:
        """
        Get the file name for the primary segmentation output.
        If no primary segmentation key is set, return None.
        """
        if self.primary_segmentation_key is None:
            return None
        return self.segmentation_paths.get(self.primary_segmentation_key)

    def validate(self) -> None:
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

    def set_primary_segments_visible(self, new_state: bool) -> None:
        """
        Sets the visibility of all child segments for the primary segmentation
        :param new_state: Whether they segment should be visible or not
        """
        display_node = self.primary_segmentation_node.GetDisplayNode()

        display_node.SetAllSegmentsVisibility(new_state)
