from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Callable

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


# Track when slicer is about to quit so we don't crash it when
#   closing as a result of trying to disable markup placement.
# KO: Why the fuck is Slicer this incapable of working correctly?
#   Far as I can tell, this error is because they don't bother to
#   clean up their QT signals until *after* they close the program,
#   which results in Python-side objects which call signal-emitting
#   functions (in this case, slicer.app.ApplicationLogic) crashing
#   QT when they try to access a no-longer-existing object. Brilliant!
SLICER_IS_RUNNING = True
@qt.Slot()
def onSlicerQuit():
    global SLICER_IS_RUNNING
    SLICER_IS_RUNNING = False
slicer.app.aboutToQuit.connect(onSlicerQuit)


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
@dataclass
class MarkupNodeMetaData:
    """
    Data class for organizing elements related to a single Markup Node
    managed by a data unit. Tracks the node its bound too alongside
    details relevant to how it should be managed and presented to the
    user, including:

    * What labels are currently tracked for it
    * What labels are expected to be placed
    * What labels are expected to be unique
    # TODO
    * The values each label should have when saved to NIfTI
    """
    bound_node: "slicer.vtkMRMLMarkupsFiducialNode"
    tracked_labels: list[str]
    required_labels: set[str]
    unique_labels: set[str]


class MarkupModelManager:

    MODEL_HEADERS = ["Label", "Count"]
    LABEL_IDX = 0
    COUNT_IDX = 1

    def __init__(self, unit: "MarkupUnit"):
        # Bound unit
        self._unit: "MarkupUnit" = unit

        # Managed model + tracked labels
        self._model = qt.QStandardItemModel()

        # Tracked metadata
        self.metadata_map: dict[str, MarkupNodeMetaData] = dict()
        self._unique_labels: dict[str, set[str]] = dict()
        self.labels_not_placed_yet: set[tuple[str, str]] = set()
        self.missing_required_labels: set[tuple[str, str]] = set()
        self.should_be_unique_labels: set[tuple[str, str]] = set()

        # Pseudo-signal, I can't be fucked to deal with QT right now
        self._call_when_missing_changes = list()

        # Run a reset to ensure we're in the same state post-reset as post-init
        self.reset()

    @property
    def model(self):
        return self._model

    def reset(self):
        # Reset the model
        self._model.clear()
        self._model.setHorizontalHeaderLabels(self.MODEL_HEADERS)

        # Clear our
        self.metadata_map.clear()
        self.labels_not_placed_yet.clear()
        self.missing_required_labels.clear()
        self.should_be_unique_labels.clear()

        # Emit the "missing labels changed" signal
        self.label_counts_changed()

    def find_next_missing(self, startIdx: qt.QModelIndex = None) -> qt.QModelIndex:
        """
        Depth-first search of the tree, checking to find the next label from this starting
        point which has yet to be placed within its owning markup. Returns None if there
        were no labels with missing placements past the provided starting point.
        """
        # If we already know we have no missing markups left, end here
        if len(self.labels_not_placed_yet) < 1:
            return qt.QModelIndex()

        # If no starting point was given, start at the beginning!
        if startIdx is None:
            idx: qt.QModelIndex = self.model.index(0, self.LABEL_IDX)
            idx = idx.child(0, self.LABEL_IDX)
        # If this is a parent index, step to the first child node instead
        elif startIdx.parent() == self.model.invisibleRootItem():
            idx = startIdx.child(0, self.LABEL_IDX)
        # Otherwise, iterate to the index immediately after this
        else:
            idx = startIdx.sibling(startIdx.row()+1, self.LABEL_IDX)
            # If this was invalid, jump to the next valid index instead
            if not idx.isValid():
                idx = self._find_first_valid_node_child_idx(startIdx)
                # If it's STILL not valid, there's nothing left to search; end here
                if idx is None:
                    return qt.QModelIndex()

        # From here, check each index until we find the next missing value.
        while idx.isValid():
            # If this row has less than 1 recorded entries, we found one!
            countIdx = self.model.sibling(idx.row(), self.COUNT_IDX, idx)
            countItem: qt.QStandardItem = self.model.itemFromIndex(countIdx)
            if int(countItem.text()) < 1:
                return idx

            # Otherwise, proceed to the next index
            newIdx = self.model.sibling(idx.row()+1, self.LABEL_IDX, idx)
            if newIdx.isValid():
                idx = newIdx
            # If the new index was invalid, we stepped out of the current node
            # and need to jump to the next one
            else:
                idx = self._find_first_valid_node_child_idx(idx)
                # If that failed, we ran out of nodes; return empty-handed
                if idx is None:
                    return qt.QModelIndex()

        # Otherwise, return empty-handed
        return qt.QModelIndex()

    # Helper alias
    def _find_first_valid_node_child_idx(self, idx):
        """
        Finds the first valid node w/ a valid child index and returns the
        CHILD index to further use.
        """
        potentialIdx = qt.QModelIndex()
        # At this point we can safely assume the index is valid and depth 2
        parentIdx = idx.parent().sibling(idx.parent().row() + 1, self.LABEL_IDX)
        while not potentialIdx.isValid():
            # If this parent index is now invalid, return empty-handed
            if not parentIdx.isValid():
                return None
            # Otherwise, update the index to be the first child
            potentialIdx = parentIdx.child(0, self.LABEL_IDX)
            # Proceed to the next parent
            parentIdx = parentIdx.sibling(parentIdx.row() + 1, self.LABEL_IDX)
        return potentialIdx

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

            # Create a new markup node details object to track the data within
            markup_config = EditableMarkupResourceConfig(resource_config, k)
            metadata = MarkupNodeMetaData(
                node,
                [mrk.label for mrk in markup_config.markups],
                {mrk.label for mrk in markup_config.markups if mrk.required},
                {mrk.label for mrk in markup_config.markups if mrk.unique},
            )
            self.metadata_map[k] = metadata

            # Get the display node to set the color
            display_node = node.GetDisplayNode()

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

        # Get the label + metadata for markup node we'll be processing
        node_label = parentItem.text()
        metadata = self.metadata_map.get(node_label)
        node = metadata.bound_node

        # If there was no matching node, something broke, end here
        if metadata is None or node is None:
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
            # Check the validity of the node
            label_tuple = (node_label, label)
            # If the label is not placed, track it
            if count < 1:
                self.labels_not_placed_yet.add(label_tuple)
                # If it should be, track that as well
                if label in metadata.required_labels:
                    self.missing_required_labels.add(label_tuple)
            # Otherwise, just purge it from their respective sets
            else:
                if label_tuple in self.labels_not_placed_yet:
                    self.labels_not_placed_yet.remove(label_tuple)
                if label_tuple in self.missing_required_labels:
                    self.missing_required_labels.remove(label_tuple)

            # If the label is unique and has more than one, track it
            if count > 1 and label in metadata.unique_labels:
                self.should_be_unique_labels.add(label_tuple)
            # Otherwise, purge it from the set instead
            else:
                if label_tuple in self.should_be_unique_labels:
                    self.should_be_unique_labels.remove(label_tuple)

        # To ensure consistent ordering, create the children in the order of our expected labels first
        for l in metadata.tracked_labels:
            _new_item(l)

        # Add remaining labels as additional columns
        remaining_labels = set(label_count.keys()) - set(metadata.tracked_labels)
        for l in remaining_labels:
            _new_item(l)

        # Emit the "labels count changed" signal to sync the warning panel
        self.label_counts_changed()

        # Finally, recount our own set of labels as well
        idx: qt.QModelIndex = parentItem.index().sibling(parentItem.row(), self.COUNT_IDX)
        nodeCountItem: qt.QStandardItem = self.model.itemFromIndex(idx)
        nodeCountItem.setText(str(node.GetNumberOfControlPoints()))

    # Pseudo-QT Signal
    # TODO: Replace this when I have the mental capacity to do this properly
    def when_label_counts_change(self, f: "Callable"):
        self._call_when_missing_changes.append(f)

    def label_counts_changed(self):
        for f in self._call_when_missing_changes:
            f()


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
        self.markupModelManager: MarkupModelManager = MarkupModelManager(self)

        # Callback for when the user finished marking up the page
        self._interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        self._originalInteractionMode = None
        self._interactionModeChangeCallbackID = None

        # Generate the VTK observers for each markup node we're managing
        self._node_observer_map = dict()

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
        # If we have an active interaction callback, clear it
        if self._interactionModeChangeCallbackID is not None:
            self._interactionNode.RemoveObserver(
                self._interactionModeChangeCallbackID
            )
            self._interactionModeChangeCallbackID = None

        # Remove all node observers
        for node, observer_list in self._node_observer_map.items():
            for observer in observer_list:
                node.RemoveObserver(observer)

    def _rebuild_observers(self):
        # Clear existing observers first
        self._clear_observers()

        # Re-initialize node-based observers for all the editable markup nodes we're managing
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
            self._node_observer_map[node] = observer_list

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
        self._selectNode(targetNode)

        # Change the default markup placement name to match the label
        targetNode.SetControlPointLabelFormat(label)

        # Begin placement
        self._interactionNode.SetCurrentInteractionMode(self._interactionNode.Place)

    def placeNextMissing(self, prior: qt.QModelIndex = None):
        """
        Begin placing the markups, starting from the previously provided item (if given).
        """
        # Track the current interaction mode, if we're not already in our custom state
        if self._interactionModeChangeCallbackID is None:
            self._originalInteractionMode = (
                self._interactionNode.GetCurrentInteractionMode()
            )
        # Otherwise, remove our old interaction state callback
        else:
            # If this was an attempt to restart, do nothing
            if prior is None:
                return
            # Otherwise, pop our old observer and start again
            self._interactionNode.RemoveObserver(self._interactionModeChangeCallbackID)

        # Find the next missing node from this point
        currentIdx = self.markupModelManager.find_next_missing(prior)

        # If there was none, we're done! Restore the original interaction state
        if not currentIdx.isValid():
            # Return to the original placement mode
            if self._originalInteractionMode is not None:
                self._interactionNode.SetCurrentInteractionMode(
                    self._originalInteractionMode
                )
            # Clear our metadata
            self._interactionModeChangeCallbackID = None
            self._originalInteractionMode = None
            # End
            return

        # Initiate label placement
        currentItem = self.markupModelManager.model.itemFromIndex(currentIdx)
        node_id = currentItem.parent().text()
        label = currentItem.text()
        self.beginLabelPlacement(node_id, label)

        # Prepare to start again from this point when the user places (or skips) the next label
        @qt.Slot()
        def _markupPlacedOrSkipped(__, ___):
            self.placeNextMissing(currentIdx)
        self._interactionModeChangeCallbackID = self._interactionNode.AddObserver(
            self._interactionNode.InteractionModeChangedEvent, _markupPlacedOrSkipped
        )

    @staticmethod
    def _selectNode(targetNode: "vtk.vtkMRMLMarkupsNode"):
        """
        Selects a node in Slicer, making it the target for any newly placed markup entries
        """
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(targetNode.GetID())

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

        # TODO: Revisit this when a better approach can be discussed.
        # # Add a "custom" node for the user to place arbitrary markups within
        # custom_node = create_emtpy_markup_fiducial_node(
        #     f"custom [{self.uid}]", scene=self.scene
        # )
        # name = f"{MarkupResource.format_for_gui('custom')} [{self.uid}]"
        # custom_node.SetName(name)
        # self.markup_nodes["custom"] = custom_node

    def focus_gained(self) -> None:
        super().focus_gained()

        # Restore the cyclic link, as Python is too dumb to manage it otherwise
        self.markupModelManager._unit = self

        # Select our first markup node to avoid potentially placing markups in previous nodes
        firstNode: "vtk.vtkMRMLMarkupsNode" = iter(
            self.markup_nodes.values()
        ).__next__()
        self._selectNode(firstNode)

        # Restore observers
        self._rebuild_observers()

    def focus_lost(self) -> None:
        super().focus_lost()

        # Clear active observers for this unit
        self._clear_observers()

        # Python should handle cycling links; it does not for some reason
        self.markupModelManager._unit = None
