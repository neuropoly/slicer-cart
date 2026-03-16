from pathlib import Path

import slicer

from CARTLib.utils.data import (
    CARTStandardUnit,
    create_empty_segmentation_node,
    load_segmentation,
)

class SegmentationUnit(CARTStandardUnit):
    """
    DataUnit for the segmentation task. Extends the CART
    Standard Unit to support custom segmentations.
    """

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ) -> None:
        super().__init__(case_data, data_path, scene)

        # Subset of segmentation nodes marked "custom"
        self._custom_segmentations = dict()

    @property
    def custom_segmentations(self):
        # Get only to avoid unintentional de-sync
        return self._custom_segmentations

    def add_custom_segmentation(self, name: str, color_hex: str):
        """
        Create a new "custom" segmentation for this data unit;
        these segmentations allow users to "add" new elements
        to the dataset.

        :return: The newly created segmentation node.
        """
        formatted_name = f"{name} ({self.uid})"
        if formatted_name in self._custom_segmentations.keys():
            raise ValueError(
                f"Cannot create custom segmentation '{name}'; "
                "a segmentation with that name already exists!"
            )

        # Create and track the new segmentation node
        new_node = None
        try:
            # Create the new node
            new_node = create_empty_segmentation_node(
                formatted_name,
                reference_volume=self.primary_volume_node,
                scene=self.scene,
            )

            # Add a new (blank) segment within the node for the user to edit
            segmentation_node = new_node.GetSegmentation()
            segment_id = segmentation_node.AddEmptySegment(name, "1")
            segment = segmentation_node.GetSegment(segment_id)

            # Set its color to match the one provided
            rgb_string = color_hex.lstrip("#")
            rgb = (int(rgb_string[i:i + 2], 16)/255 for i in (0, 2, 4))
            segment.SetColor(*rgb)

            # Track it for later reference
            self.custom_segmentations[formatted_name] = new_node
            self.segmentation_nodes[formatted_name] = new_node
            return new_node
        except Exception as e:
            # If this fails at any point, clean up the unit from the scene
            if new_node:
                slicer.mrmlScene.RemoveNode(new_node)
            raise e

    def _init_segmentation_nodes(self) -> None:
        """
        Modified version of the super-class, which "fills in" missing
        segmentations with blanks ones instead
        """
        # If we don't have a primary volume yet, this method was called too early
        if not self.primary_volume_node:
            raise ValueError(
                "Cannot initialize segmentation nodes prior to volume nodes!"
            )

        # Prepare to set the color of each segment
        color_table = slicer.util.getNode("GenericColors").GetLookupTable()
        c_idx = 2  # Start at 2, so newly created segments can have a unique color
        for key in self.segmentation_keys:
            seg_path = self.segmentation_paths.get(key, None)
            # Try to read from file
            if seg_path is not None:
                if seg_path.exists():
                    # Try to load the segmentation first
                    node = load_segmentation(seg_path)
                else:
                    continue
            # If no file exists, create a segmentation from scratch
            else:
                node = create_empty_segmentation_node(
                    "",
                    reference_volume=self.primary_volume_node,
                    scene=self.scene,
                )

                # Add a new (blank) segment within the node for the user to edit
                segmentation_node = node.GetSegmentation()
                segmentation_node.AddEmptySegment("", "1")

            # Set the name of the node, and align it to our primary volume
            node.SetName(f"{key} ({self.uid})")
            node.SetReferenceImageGeometryParameterFromVolumeNode(
                self.primary_volume_node
            )

            # Apply a unique color to all segments within the segmentation
            for segment_id in node.GetSegmentation().GetSegmentIDs():
                print(f"Setting color for segment '{segment_id}' in '{key}'.")
                segment = node.GetSegmentation().GetSegment(segment_id)

                # Get the corresponding color, w/ Alpha stripped from it
                segmentation_color = color_table.GetTableValue(c_idx)[:-1]
                segment.SetColor(*segmentation_color)

                # Increment the color index
                c_idx += 1
            self.segmentation_nodes[key] = node
            self.resources[key] = node
