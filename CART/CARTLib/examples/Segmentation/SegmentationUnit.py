from pathlib import Path
from typing import TYPE_CHECKING, Optional

import qt
import slicer
from slicer.i18n import tr as _

from CARTLib.utils.config import ResourceSpecificConfig
from CARTLib.utils.data import (
    CARTStandardUnit,
    MarkupResource,
    SegmentationResource,
    VolumeResource,
    create_empty_segmentation_node,
    load_segmentation,
    ReferenceVolumeResource,
)

from SegmentationConfig import ExtendedSegmentationResourceConfig

## Type Utils ##
if TYPE_CHECKING:
    # Avoid potential cyclic imports
    from SegmentationConfig import SegmentationConfig

    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt


## Resource-Specific Elements ##
class EditableSegmentationResource(SegmentationResource):

    id = "segmentation_editable"
    pretty_name = "To-Edit Segmentation"
    description = _(
        "A discrete (integer) segmentation of anatomy you want to load and edit for a given case. "
        "If a case is missing this resource, a blank segmentation will be created instead "
        "(which you can then edit). Can support multiple segmentations within a single file, "
        "as long as each has a unique 'final' integer value. "
        "\n\n"
        "Any changes made to this resource will be saved when the case is saved. "
        "You can customize the values the label(s) will have using the GUI below. "
        "Please define it to the best of your ability."
    )

    @classmethod
    def buildConfigGUI(
        cls, task_config: "DictBackedConfig", resource_id: Optional[str] = None
    ) -> "Optional[qt.QLayout]":
        # Initialize the layout as before
        layout = super().buildConfigGUI(task_config, resource_id)

        # Add an QTableWidget to display the segments associated w/ this resource
        resource_config = ExtendedSegmentationResourceConfig(ResourceSpecificConfig(task_config), resource_id)
        resource_config.buildSegmentTableGUI(layout)

        return layout

    def generate_user_warning(self, uid: str, resource_name: str = "") -> Optional[str]:
        # If the user hasn't specified a resource name yet, give them a more intelligent warning
        if resource_name == "":
            return _("⚠ Output files will be the same as the reference volume file "
                     "with the resource name appended! ⚠")
        # Otherwise, use the name
        return _(f"⚠ Output files are the reference volume's filename with the "
                 f"resource name appended (i.e. '{uid}_{resource_name}.nii.gz')! ⚠")


class ReferenceSegmentationResource(SegmentationResource):

    id = "segmentation_view_only"
    pretty_name = "To-View Segmentation"
    description = _(
        "A discrete (integer) segmentation of anatomy you want to load for reference. "
        "Nothing is done if a case is missing this resource; it is simply skipped over. "
        "\n\n"
        "While you can edit this segmentation in Slicer if you so choose, "
        "any changes made will **NOT** be saved when the case is saved."
    )

    @classmethod
    def buildConfigGUI(
        cls, task_config: "DictBackedConfig", resource_id: Optional[str] = None
    ) -> "Optional[qt.QLayout]":
        # Initialize the layout as before
        layout = super().buildConfigGUI(task_config, resource_id)

        # Add an QTableWidget to display the segments associated w/ this resource
        resource_config = ExtendedSegmentationResourceConfig(
            ResourceSpecificConfig(task_config), resource_id
        )
        resource_config.buildSegmentTableGUI(layout)

        return layout


class SegmentationUnit(CARTStandardUnit):
    """
    DataUnit for the segmentation task. Extends the CART
    Standard Unit to support custom segmentations.
    """

    # Replace the default segmentation resource w/ our custom subtypes
    RESOURCE_TYPES = {v.id: v for v in [
        ReferenceVolumeResource,
        VolumeResource,
        EditableSegmentationResource,
        ReferenceSegmentationResource,
        MarkupResource
    ]}

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        prior_data: dict = None,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ) -> None:
        # Replace entries in our case data w/ our custom overrides
        if prior_data is not None:
            for k, v in prior_data.items():
                case_data[k] = v

        super().__init__(case_data, data_path, scene)

    def apply_segmentation_configs(self, task_config: "SegmentationConfig"):
        """
        Apply the user-specified configuration options to the segmentations managed by
        this unit. This includes;

        * Renaming and recoloring existing segments
        * Creating missing segmentations (and segments)
        * Tracking the segmentations which should be saved
        """
        resource_config_manager = ResourceSpecificConfig(task_config)
        for k in resource_config_manager.backing_dict.keys():
            # Skip over non-segmentation resources
            if not SegmentationResource.is_type(k):
                continue
            # If there's no config options for this resource, proceed w/o doing anything
            if resource_config_manager.backing_dict.get(k) is None:
                continue
            # Updated/add the segmentation corresponding to this resource's configuration settings
            segmentation_config = ExtendedSegmentationResourceConfig(resource_config_manager, k)
            segmentation_node = self.segmentation_nodes.get(k)

            # If there is no matching segmentation (can happen w/ corrupted configs), end here
            if segmentation_node is None:
                continue

            # Make sure all "to-edit" segmentations have at least one segment in them
            should_edit = EditableSegmentationResource.is_type(k)
            if should_edit:
                # If there wasn't a node at all, create one:
                if segmentation_node is None:
                    self._create_new_segmentation(k)
                # If there was a node, but no segments in it, add a binary one:
                elif (segmentation := segmentation_node.GetSegmentation()).GetNumberOfSegments() < 1:
                    segment_id = segmentation.AddEmptySegment("", "1")
                    segment = segmentation.GetSegment(segment_id)
                    segment.SetLabelValue(1)

            # Iterate through our segment config and apply them whenever we have a match
            segmentation = segmentation_node.GetSegmentation()
            missing_segments = list()
            for segment_config in segmentation_config.segments:
                seg_val = segment_config.get(
                    ExtendedSegmentationResourceConfig.VALUE_KEY
                )
                seg_color = segment_config.get(
                    ExtendedSegmentationResourceConfig.COLOR_KEY
                )
                seg_name = segment_config.get(
                    ExtendedSegmentationResourceConfig.NAME_KEY
                )

                # Try and find the segment w/ the matching value
                was_found = False
                for segment in map(
                    lambda i: segmentation.GetNthSegment(i),
                    range(segmentation.GetNumberOfSegments()),
                ):
                    # If we did, update the segment's settings to match and finish the loop
                    if segment.GetLabelValue() == seg_val:
                        # Set its name to match
                        segment.SetName(seg_name)

                        # Set its color to match
                        rgb_string = seg_color.lstrip("#")
                        rgb = (int(rgb_string[i : i + 2], 16) / 255 for i in (0, 2, 4))
                        segment.SetColor(*rgb)

                        # End the loop early, marking this segment config as having been found
                        was_found = True
                        continue

                # If we never found a matching segment, track it for later
                if not was_found:
                    missing_segments.append(segment_config)

            # Create any missing segments
            for segment_config in missing_segments:
                seg_val = segment_config.get(
                    ExtendedSegmentationResourceConfig.VALUE_KEY
                )
                seg_color = segment_config.get(
                    ExtendedSegmentationResourceConfig.COLOR_KEY
                )
                seg_name = segment_config.get(
                    ExtendedSegmentationResourceConfig.NAME_KEY
                )

                # Generate a new empty segment to hold everything in
                segment_id = segmentation.AddEmptySegment("", seg_name)
                segment = segmentation.GetSegment(segment_id)

                # Set its color to match
                rgb_string = seg_color.lstrip("#")
                rgb = (int(rgb_string[i : i + 2], 16) / 255 for i in (0, 2, 4))
                segment.SetColor(*rgb)

                # Set its label value
                segment.SetLabelValue(seg_val)

    def _create_new_segmentation(self, name: str):

        # Create the new node
        new_node = create_empty_segmentation_node(
            name,
            reference_volume=self.reference_volume_node,
            scene=self.scene,
        )

        # Track it for later reference
        self.segmentation_nodes[name] = new_node

        # TODO Add it to this unit's subject as well

    def _load_segmentation_nodes(self, segmentation_paths: dict[str, Path]) -> None:
        """
        Modified version of the super-class, which "fills in" missing
        segmentations with blanks ones instead
        """
        # If we don't have a primary volume yet, this method was called too early
        if not self.reference_volume_key:
            raise ValueError(
                "Cannot initialize segmentation nodes prior to volume nodes!"
            )

        # Slight optimization via aliased property
        reference_volume = self.reference_volume_node

        # Ensure each segment has a unique color by default, even if the user didn't specify it.
        color_table = slicer.util.getNode("GenericColors").GetLookupTable()
        c_idx = 2  # Start at 2, so newly created segments can have a unique color
        for key, path in segmentation_paths.items():

            # Try to read from file
            if path is not None:
                if path.exists():
                    # Try to load the segmentation first
                    node = load_segmentation(path)
                # If there was a path specified, but it no longer exists, raise an error
                else:
                    raise ValueError(f"Tried to load segmentation from path {path} which doesn't exist!")

            # If no file exists, create a segmentation from scratch
            else:
                node = create_empty_segmentation_node(
                    "",
                    reference_volume=reference_volume,
                    scene=self.scene,
                )

                # Add a new (blank) segment within the node for the user to edit
                segmentation_node = node.GetSegmentation()
                segmentation_node.AddEmptySegment("", "1")

            # Determine the name this segmentation should have
            if EditableSegmentationResource.is_type(key):
                pretty_name = EditableSegmentationResource.format_for_gui(key)
            else:
                pretty_name = ReferenceSegmentationResource.format_for_gui(key)
            pretty_name = f"{pretty_name} [{self.uid}]"
            node.SetName(pretty_name)

            # Align it to our primary volume
            node.SetReferenceImageGeometryParameterFromVolumeNode(self.reference_volume_node)

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
