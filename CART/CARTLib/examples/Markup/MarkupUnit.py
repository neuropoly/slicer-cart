from pathlib import Path
from typing import Optional, TYPE_CHECKING

import ctk
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


if TYPE_CHECKING:
    # VTK is only used in the context of type checking
    import vtk

    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


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

        # Add a color selection button to choose the markups
        colorPickerButton = ctk.ctkColorPickerButton(None)
        colorPickerButton.setColor(qt.QColor(resource_config.color))
        colorPickerLabel = qt.QLabel(_("Markup Color"))
        layout.addRow(colorPickerLabel, colorPickerButton)

        @qt.Slot(qt.QColor)
        def onColorChanged(newColor: qt.QColor):
            resource_config.color = newColor.name()

        colorPickerButton.colorChanged.connect(onColorChanged)

        # Add the resource table
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

    ## Setup ##
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

        # Initialize a model to track the to-be-placed markups for this unit
        self.markupModel: qt.QStandardItemModel = qt.QStandardItemModel(0, 1, None)
        self.markupModel.setHorizontalHeaderLabels([_("Markup Points")])

    def apply_markup_configs(self, job_profile):
        """
        Apply the user-specified configuration options to the markups managed by
        this unit. This includes;

        * Applying color settings to the markups
        * Tracking the markup entries which should be saved
        * Identifying pre-existing "expected" markups
        """
        # Initialize the resource-specific configuration instance
        resource_config_manager = ResourceSpecificConfig(job_profile)

        # Iterate through its contents to apply our markup data
        markup_map: dict[str, dict[str, set[int]]] = dict()
        for k, v in resource_config_manager.backing_dict.items():
            # Skip if there is no configuration to apply for this resource
            if v is None:
                continue
            # Skip over non-editable Markup resources as well
            if not EditableMarkupResource.is_type(k):
                continue

            # Get the associated config options + markup node
            markup_node = self.markup_nodes.get(k)

            # If there was no valid node found (i.e. this case doesn't have the resource), end here
            if markup_node is None:
                continue

            # Get the display node to set the color
            display_node = markup_node.GetDisplayNode()

            # Get the configuration options for this resource
            markup_config = EditableMarkupResourceConfig(resource_config_manager, k)

            # Set the color of all markups for this node
            rgb_string = markup_config.color.lstrip("#")
            rgb = (int(rgb_string[i : i + 2], 16) / 255 for i in (0, 2, 4))
            display_node.SetSelectedColor(*rgb)

            # Update the markup up w/ this config's contents
            self._map_configured_markup_points(k, markup_config, markup_node, markup_map)

        # Use the map to (re-)generate our model
        self._reset_model()
        root: qt.QStandardItem = self.markupModel.invisibleRootItem()
        for markup_node_label, markups in markup_map.items():
            # Create the "root" markup label
            nodeItem = qt.QStandardItem(markup_node_label)
            nodeItem.setFlags(nodeItem.flags() & ~qt.Qt.ItemIsEditable)
            root.appendRow(nodeItem)
            # Add a sub-entry for each specific markup point beneath
            for markup_label, markup_points in markups.items():
                markupItem = qt.QStandardItem(markup_label)
                markupItem.setFlags(markupItem.flags() & ~qt.Qt.ItemIsEditable)
                nodeItem.appendRow(markupItem)
                # Add a sub-sub-entry for each entry which already exists
                for p in markup_points:
                    pointItem = qt.QStandardItem(str(p))
                    pointItem.setFlags(pointItem.flags() & ~qt.Qt.ItemIsEditable)
                    markupItem.appendRow(pointItem)

    def _reset_model(self):
        # Reset the model's state back to "blank" for re-population
        self.markupModel.clear()
        self.markupModel.setHorizontalHeaderLabels([_("Markup Points")])

    @staticmethod
    def _map_configured_markup_points(
        label,
        markup_config: EditableMarkupResourceConfig,
        markup_node: "vtk.vtkMRMLMarkupsFiducialNode",
        markup_map: dict[str, dict[str, set[int]]],
    ):
        # Map the existing markups within the node to the config
        config_markups = markup_config.markups
        markups_map: dict[str, set[int]] = dict()

        # Check every markup config for matches w/ the markup node's initial values
        for mrk in config_markups:
            # Initialize the entry set
            entry_set: set[int] = markups_map.get(mrk.label, set())

            # Check each control point within the markup node
            for i in range(markup_node.GetNumberOfControlPoints()):
                node_label = markup_node.GetNthControlPointLabel()
                # If it matches natively, track it for later
                if mrk.label == node_label:
                    entry_set.add(i)
                # If this config has a search value as well, check that too
                elif mrk.value is not None:
                    # TODO: check against the original int value instead
                    try:
                        config_val = int(mrk.value)
                        int_label = int(node_label)
                        if config_val == int_label:
                            entry_set.add(i)
                    except ValueError:
                        # Value errors just mean one of the values was null
                        pass

            # Insert the now-updated entry set into the map for later
            markups_map[mrk.label] = entry_set

        # Track the markup map for later
        markup_map[label] = markups_map

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
