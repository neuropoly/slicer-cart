from pathlib import Path
from typing import Optional

import qt
import slicer
from slicer.i18n import tr as _

from CARTLib.utils.config import ResourceSpecificConfig
from CARTLib.utils.data import (
    MarkupResource,
    CARTStandardUnit,
    load_markups,
    create_emtpy_markup_fiducial_node,
    ReferenceVolumeResource,
    VolumeResource,
    SegmentationResource,
)

from MarkupConfig import EditableMarkupResourceConfig


class EditableMarkupResource(MarkupResource):

    id = "markup_editable"
    pretty_name = "To-Edit Markup"
    user_warning = _(
        "⚠ The resource name will be used as a suffix in the saved file! ⚠"
    )
    description = _(
        "A set of markups to display over viewed volumes. "
        "If a case is missing this resource, a blank markup node will be created instead "
        "(which you can then edit). Can support multiple markup points within a single file. "
        "\n\n"
        "Any changes made to this resource will be saved when the case is saved. "
        "You can specify what markups you expect to see, as well as their properties, in the"
        "GUI below. The 'value' column is only used when reading/writing to NiFTI format."
    )

    @classmethod
    def buildConfigGUI(
        cls, task_config: "DictBackedConfig", resource_id: Optional[str] = None
    ) -> "Optional[qt.QLayout]":
        # Initialize the backing config instance to better isolate these options from the "global" ones
        resource_handling_config = ResourceSpecificConfig(task_config)

        # Initialize the resource-specific config instance
        resource_config = EditableMarkupResourceConfig(
            resource_handling_config, resource_id
        )

        # Initialize a layout to wrap its GUI
        layout = qt.QFormLayout(None)
        resource_config.buildMarkupTableGUI(layout)

        # Return the result
        return layout


class MarkupUnit(CARTStandardUnit):

    # Replace the default Markup resource w/ our custom ones
    RESOURCE_TYPES = {v.id: v for v in [
        ReferenceVolumeResource,
        VolumeResource,
        SegmentationResource,
        EditableMarkupResource,
        MarkupResource,
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

        # Initialize as normal
        super().__init__(case_data, data_path, scene)

    def _load_markups_nodes(self, markup_paths: dict[str, Path]) -> None:
        # Ensure each "editable" markup has a corresponding node
        for key, path in markup_paths.items():
            # Try to read from file
            if path is not None:
                if path.exists():
                    # Try to load the markups naturally first
                    nodes = load_markups(path)
                # If there was a path specified, but it no longer exists, raise an error
                else:
                    raise ValueError(
                        f"Tried to load markup from path {path} which doesn't exist!"
                    )

            # If this an editable markup and there wasn't a file to load from,
            # generate a blank node instead
            elif EditableMarkupResource.is_type(key):
                nodes = [create_emtpy_markup_fiducial_node(
                    f"{key} [{self.uid}]",
                    scene=self.scene,
                )]

            # Label the markups iteratively if there are multiple
            should_iter = len(nodes) > 1
            for i, node in enumerate(nodes):
                # Error out if the node is the wrong type (currently only fiducials are supported)
                if not isinstance(node, slicer.vtkMRMLMarkupsFiducialNode):
                    raise TypeError(
                        f"Expected a MarkupsFiducialNode, got {type(node)} for key {key}."
                    )
                # Determine how the node should be named
                if should_iter:
                    name = f"{MarkupResource.format_for_gui(key)} [{self.uid} - {i}]"
                else:
                    name = f"{MarkupResource.format_for_gui(key)} [{self.uid}]"
                # Update the node's properties and track it
                node.SetName(name)
                self.markup_nodes[key] = node

        # Add a "custom" node for the user to place arbitrary markups within
        custom_node = create_emtpy_markup_fiducial_node(
            f"custom [{self.uid}]", scene=self.scene
        )
        name = f"{MarkupResource.format_for_gui('custom')} [{self.uid}]"
        custom_node.SetName(name)
        self.markup_nodes["custom"] = custom_node
