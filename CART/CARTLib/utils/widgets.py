import slicer

# The code below does actually work, but the Slicer widgets are only added
#  to the namespace after slicer boots, hence the error suppression
# noinspection PyUnresolvedReferences
import qSlicerSegmentationsModuleWidgetsPythonQt


class CARTSegmentationEditorWidget(qSlicerSegmentationsModuleWidgetsPythonQt.qMRMLSegmentEditorWidget):
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

    def __init__(
            self,
            tag: str = "CARTSegmentEditor",
            scene = slicer.mrmlScene
    ):
        """
        Create a new segmentation editor widget.

        By default, it will be identical to the widget used in the Segment
        Editor module, to the point of sharing its current state.

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

    def _set_up_editor_node(self):
        # Get a pre-existing node from the MRML scene if it exists
        editor_node = \
            self.scene.GetSingletonNode(self.tag, self.SEGMENT_EDITOR_NODE_KEY)

        # If we don't have one, create it ourselves
        if not editor_node:
            editor_node = self.scene.CreateNodeByClass(self.SEGMENT_EDITOR_NODE_KEY)
            editor_node.UnRegister(None)
            editor_node.SetSingletonTag(self.tag)
            # Update ourselves to use this editor node
            self.scene.AddNode(editor_node)

        # Update ourselves to use this editor node
        self.setMRMLSegmentEditorNode(editor_node)

        # Track the editor node for future reference
        self.editor_node = editor_node

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

