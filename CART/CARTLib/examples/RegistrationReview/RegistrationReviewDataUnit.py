import slicer


from pathlib import Path


from CARTLib.examples.MultiContrastSegmentation.MultiContrastSegmentationEvaluationDataUnit import (
    MultiContrastSegmentationEvaluationDataUnit,
)
from CARTLib.utils.data import (
    load_segmentation,
)
from CARTLib.utils.layout import LayoutHandler, Orientation


class RegistrationReviewDataUnit(MultiContrastSegmentationEvaluationDataUnit):
    """
    A data unit for the Registration Review task.
    This data unit is used to manage the resources needed for the Registration Review task,
    including volumes, segmentations, and markups.
    """

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,  # Scene is NOT optional.
        # Default scene is the global MRML scene, which is always available.
    ):
        super().__init__(case_data, data_path, scene)

    def _init_segmentation_nodes(self) -> None:
        """
        For each segmentation key, load if file exists.
        This only differs from the base class by not creating a new empty segmentation node for the primary segmentation.
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
            else:
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

    def set_foreground_opacity(self, opacity: float):
        """Set the foreground opacity for the layout handler."""
        self.layout_handler.set_foreground_opacity(opacity)
