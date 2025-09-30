from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _

# The code below does actually work, but the Slicer widgets are only added
#  to the namespace after slicer boots, hence the error suppression
# noinspection PyUnresolvedReferences
import qSlicerSegmentationsModuleWidgetsPythonQt

## Standardized Prompts ##
def showSuccessPrompt(msg: str, parent_widget: Optional[qt.QWidget] = None):
    """
    Show a standardized QT prompt for something being successful.

    Blocks interactions until closed (modal); you should provide a
    parent widget to "block" to avoid cross-modal blocking if possible
    """
    # Build the prompt itself
    msgPrompt = qt.QMessageBox(parent_widget)
    msgPrompt.setWindowTitle(_("SUCCESS!"))

    # Display the requested text within it, and show it to the user
    msgPrompt.setText(msg)
    msgPrompt.exec()


def showErrorPrompt(msg: str, parent_widget: Optional[qt.QWidget]):
    # Build the prompt itself
    errBox = qt.QErrorMessage(parent_widget)
    errBox.setWindowTitle(_("ERROR!"))

    # Display the requested text within it, and show it to the user
    errBox.showMessage(msg)
    errBox.exec()


## CART-Tuned Segmentation Editor ##
class _NodeComboBoxProxy(qt.QComboBox):
    """
    A combobox widget which delegates to a proxy `qMRMLNodeComboBox` to run operations
    in the code.

    This is required because there is no way to refresh a `qMRMLNodeComboBox` to check
    whether the node's its tracking have become hidden since it initialized. This is
    the only way to allow access to (and modification of
    """

    def __init__(self, bound_widget: slicer.qMRMLNodeComboBox, *args):
        super().__init__(*args)

        # Reference to its "bound" widget which we will be instructing instead.
        self._bound_widget = bound_widget

        # Isolate the bound widget's ComboBox, as we will update it by-proxy
        self._combo_box = self._findComboBox()

        # Map from our indices to those used by the bound widget's
        self.idx_map: dict[int, int] = dict()

        # Slots are an affront to god
        self.currentIndexChanged.connect(self.onIndexChanged)

        # Initialize via a refresh
        self.refresh()

    def _findComboBox(self):
        # Search the children of our bound widget to a ComboBox of some kind
        for c in self._bound_widget.children():
            # KO: despite ctkComboBox explicitly being a subclass of QComboBox, the
            #  developers failed to translate that relationship to Python. hence us
            #  checking for both
            if isinstance(c, qt.QComboBox) or isinstance(c, ctk.ctkComboBox):
                return c

    def refresh(self):
        # Reset our entries before re-building
        self.clear()

        # Start by filtering through our viewed nodes
        # KO: We really should use "nodes" here, but despite it being documented as a
        #  valid method in the Slicer docs, it doesn't actually work! Ref:
        #  https://apidocs.slicer.org/main/classqMRMLNodeComboBox.html#a2313ce3b060a2a2068a117f3ea232a56
        self.idx_map = {}
        for i in range(self._bound_widget.nodeCount()):
            node = self._bound_widget.nodeFromIndex(i)
            if self._bound_widget.showHidden or not node.GetHideFromEditors():
                self.idx_map[self.count] = i
                self.addItem(node.GetName())

        # TODO: Figure out how to re-enable actions again...
        # # If we have no more entries, terminate here
        # if i >= self._combo_box.count:
        #     return
        #
        # # Any entries past this point correspond to actions w/ text labels
        # self.insertSeparator(self.count)
        # i += 2  # For some reason, inserting a separator adds two entries...
        # for i in range(i, self._combo_box.count):
        #     label = self._combo_box.itemText(i)
        #     self.idx_map[self.count] = i
        #     self.addItem(label)

    def map_index(self, idx: int):
        # Special case; -1 is universal for "nothing is selected"
        if idx == -1:
            return -1
        # Otherwise, try to get our mapped index
        mapped_idx = self.idx_map.get(idx, None)
        if mapped_idx is None:
            raise ValueError(f"Could not find requested index {idx}!")
        return mapped_idx

    def onIndexChanged(self, idx: int):
        mapped_idx = self.map_index(idx)
        self._combo_box.setCurrentIndex(mapped_idx)

    ## Proxy Parameters ##
    @property
    def addEnabled(self) -> bool:
        return self._bound_widget.addEnabled

    @addEnabled.setter
    def addEnabled(self, val: bool):
        self._bound_widget.addEnabled = val

    @property
    def removeEnabled(self) -> bool:
        return self._bound_widget.removeEnabled

    @removeEnabled.setter
    def removeEnabled(self, val: bool):
        self._bound_widget.removeEnabled = val

    @property
    def showHidden(self) -> bool:
        return self._bound_widget.showHidden

    @showHidden.setter
    def showHidden(self, val: bool):
        self._bound_widget.showHidden = val


class CARTSegmentationEditorWidget(
    qSlicerSegmentationsModuleWidgetsPythonQt.qMRMLSegmentEditorWidget
):
    """
    A "wrapper" for Segment Editor Modules's editor widget, to make it more
    user-friendly and easier to manage in the context of a CART task.

    Specifically, this automatically does some stuff that the module would have
    done instead, including:
        * Hooking itself into an MRML scene
        * Creating a `vtkMRMLSegmentEditorNode` editor node into said scene
        * Managing shortcuts for its various functions

    Code heavily based on SegmentEditorWidget in
    https://github.com/Slicer/Slicer/blob/main/Modules/Scripted/SegmentEditor/SegmentEditor.py
    """

    SEGMENT_EDITOR_NODE_KEY = "vtkMRMLSegmentEditorNode"

    def __init__(self, tag: str = "CARTSegmentEditor", scene=slicer.mrmlScene):
        """
        Create a new segmentation editor widget; basically a carbon copy of
        `qMRMLSegmentEditorWidget` with a few additions to make it play nicer with
        CART constantly replacing nodes in MRML scene.

        :param tag: The tag for the segmentation editor node in the MRML scene.
            If you want to have your editor have different active settings than
            the one in the Segment Editor module, you should specify something
            here.
        :param scene: The MRML scene this widget will hook into. By default, it
            uses Slicer's MRML scene; passing a different scene will hook into
            it instead (useful for organization purposes in some cases).
        """
        # Run initial setup first
        super().__init__()

        # Parameters tracking for ease-of-reference
        self.tag: str = tag
        self.scene = scene

        # By default, match the Segment Editor Module's 10-deep undo state buffer
        self.setMaximumNumberOfUndoStates(10)

        # Associate ourselves with our scene
        self.setMRMLScene(self.scene)

        # Initialize (and track) the segmentation editor node in the MRML scene
        self.editor_node = None
        self._set_up_editor_node()

        self.setAddRemoveSegmentButtonsVisible(True)

        # We expect the task to select the most relevant "source" volume

        # Hide "swap to Segmentations Button" as well
        self.setSwitchToSegmentationsButtonVisible(False)

        # Track our segmentation node combo box for direct reference
        self.proxySegNodeComboBox = self._replaceSegmentationSelectionNode()

        # Hide the ability to add or remove segments by default
        self.proxySegNodeComboBox.addEnabled = False
        self.proxySegNodeComboBox.removeEnabled = False

    ## Setup Helpers ##
    def _set_up_editor_node(self):
        # Get a pre-existing node from the MRML scene if it exists
        editor_node = self.scene.GetSingletonNode(
            self.tag, self.SEGMENT_EDITOR_NODE_KEY
        )

        # If we don't have one, create it ourselves
        if not editor_node:
            editor_node = self.scene.CreateNodeByClass(self.SEGMENT_EDITOR_NODE_KEY)
            editor_node.UnRegister(None)
            editor_node.SetSingletonTag(self.tag)
            self.scene.AddNode(editor_node)

        # Update ourselves to use this editor node
        self.setMRMLSegmentEditorNode(editor_node)

        # Track the editor node for future reference
        self.editor_node = editor_node

    def _replaceSegmentationSelectionNode(self) -> Optional[_NodeComboBoxProxy]:
        # Unfortunately we have to exploit QT here to search for it; Slicer hides it
        #  from public access through its interface
        for c in self.children():
            if c.name == "SegmentationNodeComboBox":
                # Build a proxy widget for it
                proxy = _NodeComboBoxProxy(c)
                # Use it to replace the original widget in the UI
                self.layout().replaceWidget(c, proxy)
                c.setVisible(False)
                # Return it, ending the search here
                return proxy

        # If we could not find it, return empty-handed
        return None

    ## UI Management ##
    def enter(self):
        # Synchronize ourselves with the MRML state
        self.updateWidgetFromMRML()
        # Install our built-in shortcuts into Slicer's hotkeys
        self.installKeyboardShortcuts()

    def exit(self):
        # Disable the active effect, as it *will* desync otherwise
        self.setActiveEffect(None)
        # Uninstall keyboard shortcuts
        self.uninstallKeyboardShortcuts()

    def refresh(self):
        self.proxySegNodeComboBox.refresh()

    def setSegmentationNode(self, segment_node):
        # KO: We need to delegate to our proxy widget here,
        # otherwise it and the "real" Slicer state will no longer
        # by in sync
        self.proxySegNodeComboBox.setCurrentText(
            segment_node.GetName()
        )
