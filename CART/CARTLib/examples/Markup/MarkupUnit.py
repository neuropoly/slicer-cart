import logging
from collections import Counter
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

from MarkupConfig import MarkupConfig, EditableMarkupResourceConfig


if TYPE_CHECKING:
    # VTK is only used in the context of type checking
    import vtk

    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


## Resources ##
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


## Markup Model ##
class MarkupModelManager:

    MODEL_HEADERS = ["Label", "Count"]

    def __init__(self, unit: "MarkupUnit"):
        # Bound unit
        self._unit: "MarkupUnit" = unit

        # Managed model + tracked labels
        self._model = qt.QStandardItemModel()

        # Tracked labels
        self._tracked_labels: dict[str, list[str]] = dict()

        # Run a reset to ensure we're in the same state post-reset as post-init
        self.reset()

    @property
    def model(self):
        return self._model

    def reset(self):
        # Reset the model
        self._model.clear()
        self._model.setHorizontalHeaderLabels(self.MODEL_HEADERS)

        # Clear the tracked label map
        self._tracked_labels.clear()

    def apply_config_settings(self, config: "MarkupConfig"):
        # Reset the model's state
        self.reset()

        # Isolate the resource-specific config instance from the job profile
        resource_config = ResourceSpecificConfig(config)

        # Iterate through its contents to generate the top-level branches
        rootItem: qt.QStandardItem = self._model.invisibleRootItem()
        for k, v in resource_config.backing_dict.items():
            # Skip if there is no configuration to apply for this resource
            if v is None:
                continue
            # Skip over non-editable Markup resources as well
            if not EditableMarkupResource.is_type(k):
                continue

            # Get the node associated with this configuration, skipping if there is none
            if (node := self._unit.markup_nodes.get(k)) is None:
                continue

            # Parse the resource's contents
            markup_config = EditableMarkupResourceConfig(resource_config, k)
            self._tracked_labels[k] = [mrk.label for mrk in markup_config.markups]

            # Get the display node to set the color
            display_node = node.GetDisplayNode()

            # Get the configuration options for this resource
            markup_config = EditableMarkupResourceConfig(resource_config, k)

            # Set the color of for this markup node's labels
            rgb_string = markup_config.color.lstrip("#")
            rgb = (int(rgb_string[i : i + 2], 16) / 255 for i in (0, 2, 4))
            display_node.SetSelectedColor(*rgb)

            # Generate and register the label + count item
            newLabelItem = qt.QStandardItem(k)
            newLabelItem.setEditable(False)
            newCountItem = qt.QStandardItem(str(node.GetNumberOfControlPoints()))
            newCountItem.setEditable(False)
            rootItem.appendRow([newLabelItem, newCountItem])

            # Generate the child items for each label
            self.rebuild_children_for(newLabelItem)

    def rebuild_children_for(self, parentItem: qt.QStandardItem):
        # Clear all existing children from this item; nature is so cruel...
        parentItem.removeRows(0, parentItem.rowCount())

        # Get the label for markup node we'll be processing
        node_label = parentItem.text()
        node = self._unit.markup_nodes.get(node_label)

        # If there was no matching node, something broke, end here
        if node is None:
            return

        # Count the existing labels within the node
        markup_iterator = range(node.GetNumberOfControlPoints())
        label_count = Counter(
            [node.GetNthControlPointLabel(i) for i in markup_iterator]
        )

        # "Macro" to avoid code duplication
        def _new_item(label: str):
            # Build the new child item
            count = label_count.get(label, 0)
            labelItem = qt.QStandardItem(label)
            labelItem.setEditable(False)
            countItem = qt.QStandardItem(str(count))
            countItem.setEditable(False)
            parentItem.appendRow([labelItem, countItem])

        # To ensure consistent ordering, create the children in the order of our expected labels first
        required_labels = self._tracked_labels[node_label]
        for l in required_labels:
            _new_item(l)

        # Add remaining labels as additional columns
        remaining_labels = set(label_count.keys()) - set(required_labels)
        for l in remaining_labels:
            _new_item(l)


class MarkupNodeItemData:
    def __init__(
        self,
        node: "vtk.vtkMRMLMarkupsNode",
        color: str,
        required_markups: list[str],
    ):
        # Additional data
        self._node: "vtk.vtkMRMLMarkupsNode" = node
        self._color: str = color
        self._required_markups: list[str] = required_markups

    @property
    def color(self):
        return self._color

    def rebuild_children_for(self, item: qt.QStandardItem):
        # Clear all existing children from this item; nature is so cruel...
        item.removeRows(0, item.rowCount())

        # Count the existing labels within our bound node
        markup_iterator = range(self._node.GetNumberOfControlPoints())
        label_count = Counter(
            [self._node.GetNthControlPointLabel(i) for i in markup_iterator]
        )

        # "Macro" to avoid code duplication
        def _new_item(l: str):
            # Build the new child item
            n = label_count.get(l, 0)
            childItem = qt.QStandardItem(l)
            childData = MarkupLabelItemData(n)
            childItem.setData(childData)

            item.appendRow(childItem)

        # To ensure consistent ordering, create the children in the order of our expected labels first
        for l in self._required_markups:
            _new_item(l)

        # Add remaining labels as additional columns
        remaining_labels = set(label_count.keys()) - set(self.expected_labels)
        for l in remaining_labels:
            _new_item(l)


class MarkupLabelItemData:
    def __init__(self, count: int):
        self.count = count


## Data Units ##
class MarkupUnit(CARTStandardUnit):

    # Replace the default Markup resource w/ our custom ones
    RESOURCE_TYPES = {v.id: v for v in [
        ReferenceVolumeResource,
        VolumeResource,
        SegmentationResource,
        EditableMarkupResource,
        MarkupResource,
    ]}

    MODEL_HEADER = ["Label", "Count"]

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

        # Tracked list of names -> nodes for later user
        self._tracked_nodes: dict["vtk.vtkMRMLMarkupsNode", str] = dict()

        # Initialize as normal
        super().__init__(case_data, data_path, scene)

        # Create a model manager to regulate our data
        self.markupModelManager = MarkupModelManager(self)

        # Generate the VTK observers for each markup node we're managing
        self._observer_map = dict()
        self._rebuild_observers()

    ## DATA MANAGEMENT ##
    @property
    def dataModel(self):
        return self.markupModelManager.model

    def apply_config(self, config: "MarkupConfig"):
        """
        Apply the user-specified configuration options to the markups managed by
        this unit. This includes;

        * Applying color settings to the markups
        * Tracking the markup entries which should be saved
        * Identifying pre-existing "expected" markups
        """
        # Delegate to the model manager
        self.markupModelManager.apply_config_settings(config)

    ## DATA OBSERVERS ##
    def _clear_observers(self):
        # Remove all observers
        for node, observer_list in self._observer_map.items():
            for observer in observer_list:
                node.RemoveObserver(observer)

    def _rebuild_observers(self):
        # Clear existing observers first
        self._clear_observers()

        # Re-initialize observers for all the editable markup nodes we're managing
        for node in self._tracked_nodes.keys():
            # Initialize a new blank list
            observer_list = list()

            # Label Changed (Added or Modified) or Deleted
            labelChangedObserver = node.AddObserver(
                node.PointModifiedEvent, self._onLabelCountChanged
            )
            labelRemovedObserver = node.AddObserver(
                node.PointRemovedEvent, self._onLabelCountChanged
            )

            observer_list.append(labelChangedObserver)
            observer_list.append(labelRemovedObserver)

            # Track the list of newly created observers
            self._observer_map[node] = observer_list

    def _onLabelCountChanged(self, node, __):
        """
        Identifies which item in the model needs to have its counts updated,
        and does so.
        """
        # Find the corresponding item for this node
        model = self.markupModelManager.model
        for i in range(model.rowCount()):
            # Get the corresponding item
            item: qt.QStandardItem = model.item(i, 0)
            # Iterate through it tracked nodes to see if any match
            key = self._tracked_nodes.get(node)
            if item.text() == key:
                self.markupModelManager.rebuild_children_for(item)
                return

    ## USER INTERACTION ##
    def beginLabelPlacement(self, node_id: str, label: str):
        # Set up the selection node to focus on our specific markup
        targetNode = self.markup_nodes[node_id]
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(targetNode.GetID())

        # Change the default markup placement name to match the label
        targetNode.SetControlPointLabelFormat(label)

        # Begin placement
        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        interactionNode.SetCurrentInteractionMode(interactionNode.Place)

    ## OVERRIDES ##
    def _load_markups_nodes(self, markup_paths: dict[str, Path]) -> None:
        # Reset the track node map
        self._tracked_nodes.clear()

        # Ensure each "editable" markup has a corresponding node
        for key, path in markup_paths.items():
            # Try to read from file
            is_editable = EditableMarkupResource.is_type(key)
            if path is not None:
                if path.exists():
                    # Try to load the markups naturally first
                    nodes = load_markups(path)
                # If there was a path specified, but it no longer exists, raise an error
                else:
                    raise ValueError(
                        f"Tried to load markup from path {path} which doesn't exist!"
                    )
            # If this is supposed to be an editable node, create a block node instead
            elif is_editable:
                nodes = [create_emtpy_markup_fiducial_node(
                    f"{key} [{self.uid}]",
                    scene=self.scene,
                )]
            # Otherwise, just skip over
            else:
                continue

            # If the nodes were editable, track them
            if is_editable:
                for node in nodes:
                    self._tracked_nodes[node] = key

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

    def clean(self) -> None:
        super().clean()

        # Clear any active observers
        self._clear_observers()
