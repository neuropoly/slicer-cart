"""
Adds a number of utilities for handling the layout of viewer nodes, ensuring that they
are correctly managed as CART iterates through its cases.

Also adds some streamlining methods for common operations (i.e. creating a view node).

Heavily derived from SlicerCaseIterators `CaseIteratorLayoutLogic` class; however, this
has been restructured to be more general purpose and less prone to memory leaks.
"""

from enum import auto, Flag
from functools import cache
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _


## Orientation Helpers ##
class Orientation(Flag):
    # The "core" types
    AXIAL = auto()
    SAGITTAL = auto()
    CORONAL = auto()

    # Three-letter aliases for ease of use
    AXI = AXIAL
    SAG = SAGITTAL
    COR = CORONAL

    # "TRIO" type for representing all common orientations simultaneously
    TRIO = AXI | SAG | COR

    def slicer_node_label(self):
        """
        Returns the string representation for this orientation, formatted in the manner
        required by Slicer's vtkMRMLSliceNode class.

        As a vtkMRMLSliceNode can only handle one (singular) orientation at a time, we
        raise an error if you try to generate the string representation for multiple
        (plural) orientations at once
        """
        if not self.is_singular():
            raise ValueError(
                "No Slicer orientation string exists for non-singular Orientations!"
            )
        return str(self).split(".")[1].capitalize()

    def is_singular(self):
        return len(self) == 1

    def is_plural(self):
        return len(self) > 1

    # TODO: Remove once once we have Python 3.11+, as Flag's then have their own
    #  built-in "iter" method instead
    def __iter__(self):
        for v in [self.AXI, self.SAG, self.COR]:
            if self.__contains__(v):
                yield v

    # TODO: Remove once once we have Python 3.11+, as Flag's then have their own
    #  built-in "len" method instead
    def __len__(self):
        n = 0
        for _ in self:
            n += 1
        return n


CART_TO_SLICER_ORIENTATION = {
    Orientation.AXI: "Axial",
    Orientation.SAG: "Sagittal",
    Orientation.COR: "Coronal",
}


def snap_all_to_ijk():
    # Snap all active nodes to IJK to avoid potential rounding errors
    sliceLogics = slicer.app.layoutManager().mrmlSliceLogics()
    numLogics = sliceLogics.GetNumberOfItems()
    for n in range(numLogics):
        sliceLogic = sliceLogics.GetItemAsObject(n)
        sliceLogic.SnapSliceOffsetToIJK()


## Color Helpers ##
@cache
def layout_color(idx: int) -> str:
    """
    Get the RGB string from Slicer's default lookup table.

    Cached to avoid multiple string iterations lagging iteration in slower computers.
    """
    # Assert the index is valid (greater than 0)
    assert idx >= 0, "Cannot choose a color using a negative index!"

    # Get the lookup table from our color scheme
    colors = slicer.util.getNode("GenericColors")
    _ = colors.GetLookupTable()

    # Get the RGB tuple from the lookup table
    rgb_tuple = tuple([int(round(v * 255)) for v in lookup_color(idx)])

    # Return its string representation
    return "#%0.2X%0.2X%0.2X" % rgb_tuple


@cache
def lookup_color(idx: int) -> tuple[int, int, int]:
    """
    Get the RGB tuple from Slicer's default lookup table.

    Cached to avoid multiple string iterations lagging iteration in slower computers.
    """
    # Assert the index is valid (greater than 0)
    assert idx >= 0, "Cannot choose a color using a negative index!"

    # Get the lookup table from our color scheme
    colors = slicer.util.getNode("GenericColors")
    lookup_table = colors.GetLookupTable()

    # Get the RGB tuple from the lookup table
    return tuple(lookup_table.GetTableValue(idx)[:-1])


## Viewer Layout Management ##
class LayoutHandler:
    def __init__(
        self,
        volume_nodes: list[slicer.vtkMRMLVolumeNode],
        primary_volume_node: Optional[slicer.vtkMRMLVolumeNode] = None,
        orientation: Orientation = Orientation.AXIAL,
        horizontal_volumes: bool = True,
        foreground_opacity: float = 1.0,
    ):
        """
        Layout handler which manages the viewers for a set of volume nodes for you.

        :param volume_nodes: The list of volume nodes this layout should manage our
            viewer layout for.
        :param primary_volume_node: The primary volume node to use as background in all views.
            If None, the first volume node is used as primary.
        :param orientation: The orientation(s) that the layout should account for.
        :param horizontal_volumes: Whether the views for each volume node should be laid
            out horizontally (left-to-right). If false, they are displayed vertically
            (top-to-bottom) instead. Note that the orientations are always laid out in the
            opposite order; if volumes are laid out horizontally, orientations are laid
            out vertically, and vice versa.
        :param foreground_opacity: The opacity for foreground volumes;
            only used when the primary volume is made to be the background.
        """
        # Attributes
        self._tracked_volumes = volume_nodes
        self._primary_volume_node = primary_volume_node or (
            volume_nodes[0] if volume_nodes else None
        )
        self._orientation = orientation
        self._horizontal_volumes = horizontal_volumes
        self._foreground_opacity = foreground_opacity
        self._layout: Optional[str] = None

        # Tracked map of view names -> volume and orientation tuples
        self._view_name_map: Optional[
            dict[str, tuple[slicer.vtkMRMLVolumeNode, Orientation]]
        ] = None

        # Tracked map of slice nodes, for re-use and clean-up
        self._slice_node_map: dict[str, slicer.vtkMRMLSliceNode] = dict()

    ## Properties ##
    @property
    def layout(self) -> str:
        """
        The layout XML for this class.

        Lazily evaluated to avoid redundant regeneration whenever something about the
        layout is changed.
        """
        # Rebuild the layout first if it doesn't exist (it was invalidated, or this is
        #  the first time the layout is being requested)
        if not self._layout:
            self.rebuild_layout()
        return self._layout

    @property
    def tracked_volumes(self):
        return self._tracked_volumes

    @tracked_volumes.setter
    def tracked_volumes(self, new_volumes):
        # Update our list of tracked volumes
        self._tracked_volumes = new_volumes

        # If the old primary volume isn't in the list,
        # make the first volume in the list our new primary
        if not self._primary_volume_node in new_volumes:
            self._primary_volume_node = new_volumes[0] if new_volumes else None

        # Invalidate the current layout
        self._layout = None

    @property
    def primary_volume_node(self):
        return self._primary_volume_node

    @primary_volume_node.setter
    def primary_volume_node(self, new_volume):
        # Set the primary volume to this new volume
        self._primary_volume_node = new_volume

        # If the volume wasn't already tracked, track it
        if not new_volume in self._tracked_volumes:
            self._tracked_volumes.append(new_volume)

        # Invalidate the current layout
        self._layout = None

    @property
    def orientation(self):
        return self._orientation

    @orientation.setter
    def orientation(self, new_orientation: Orientation):
        # Special case; only invalidate the layout if the new orientation is different.
        if new_orientation != self._orientation:
            self._orientation = new_orientation
            self._layout = None

    @property
    def horizontal_volumes(self) -> bool:
        return self._horizontal_volumes

    @horizontal_volumes.setter
    def horizontal_volumes(self, new_val: bool):
        if new_val != self._horizontal_volumes:
            self._horizontal_volumes = new_val
            self._layout = None

    @property
    def vertical_volumes(self) -> bool:
        return not self._horizontal_volumes

    @vertical_volumes.setter
    def vertical_volumes(self, new_val: bool):
        if new_val == self._horizontal_volumes:
            self._horizontal_volumes = not new_val
            self._layout = None

    ## Layout Handlers ##
    def match_layout_settings_with(self, other_handler: "LayoutHandler"):
        """
        Copies the layout settings used by another handler;
        used to simulate settings being shared across multiple handlers
        (i.e. the per data-unit handlers)
        """
        self.orientation = other_handler.orientation
        self.horizontal_volumes = other_handler.horizontal_volumes

    def rebuild_layout(self):
        # If we don't have any tracked volumes yet, raise an error
        if not self.tracked_volumes:
            raise ValueError("This layout manager has no volumes to lay out!")

        # Determine how we will lay out our volumes (and each of their views)
        volume_layout = "horizontal" if self.horizontal_volumes else "vertical"
        orientation_layout = "horizontal" if self.vertical_volumes else "vertical"

        # Begin building the layout XML
        layout_xml = f'<layout type="{volume_layout}">'

        # Reset our volume name map, as we are about to rebuild it
        self._view_name_map = dict()

        # Keep track of a color index interator to update through these loops
        color_idx = 1
        for v in self.tracked_volumes:
            # Add a sub-layout for each volume node's orientations
            layout_xml += f' <item> <layout type="{orientation_layout}">\n'
            for o in self.orientation:
                # Set up our parameters to build the XML entry
                ori = o.slicer_node_label()
                name = f"{v.GetName()}--{ori}"
                color = layout_color(color_idx)
                color_idx += 1

                # Generate the corresponding XML entry and add it to our overall schema
                layout_xml += self._build_viewer_entry(name, ori, color)

                # Add the corresponding entry to our value name map
                self._view_name_map[name] = (v, ori)

            # Close the sub-layout
            layout_xml += "</layout></item>\n"

        # Close the layout
        layout_xml += "</layout>"

        # Track it for later
        self._layout = layout_xml

    def apply_layout(self):
        """
        Apply the current layout to the scene. Should be called when a given GUI needs
        to bring itself back into focus.

        TODO: Figure out a way that doesn't assume our desired layout node will be the
         first in the list of layout nodes within the MRML scene
        """
        # (Re-)Build our layout if it doesn't exist
        if not self._layout:
            self.rebuild_layout()

        # Apply our layout XML to the current scene
        layout_node = slicer.util.getNode("*LayoutNode*")
        if layout_node.IsLayoutDescription(layout_node.SlicerLayoutUserView):
            layout_node.SetLayoutDescription(
                layout_node.SlicerLayoutUserView, self.layout
            )
        else:
            layout_node.AddLayoutDescription(
                layout_node.SlicerLayoutUserView, self.layout
            )
        layout_node.SetViewArrangement(layout_node.SlicerLayoutUserView)

        # Have slicer process the new layout XML
        slicer.app.processEvents()

        # Build up our slice nodes for each of the views we have in our layout.
        layout_manager = slicer.app.layoutManager()
        for layout_name, (vol_node, ori) in self._view_name_map.items():
            # Grab the corresponding widget in our layout
            slice_widget = layout_manager.sliceWidget(layout_name)

            # Set up background and foreground volumes
            composite_node = slice_widget.mrmlSliceCompositeNode()

            # Always use primary volume as background
            if self.primary_volume_node:
                composite_node.SetBackgroundVolumeID(self.primary_volume_node.GetID())

                # If the current volume is different from primary, set it as foreground
                if vol_node != self.primary_volume_node:
                    composite_node.SetForegroundVolumeID(vol_node.GetID())
                    composite_node.SetForegroundOpacity(self._foreground_opacity)
                else:
                    # If it's the primary volume view, no foreground needed
                    composite_node.SetForegroundVolumeID("")
            else:
                # Fallback: if no primary volume, use the current volume as background
                composite_node.SetBackgroundVolumeID(vol_node.GetID())
                composite_node.SetForegroundVolumeID("")

            # Get the slice node which manages the slice the widget views
            slice_node = slice_widget.mrmlSliceNode()

            # Ensure it matches its associated volume's orientation and rotation.
            slice_node.SetOrientation(ori)
            # Use the volume for rotation, not the orientation
            rotation_volume = self.primary_volume_node or vol_node
            slice_node.RotateToVolumePlane(rotation_volume)
            slice_widget.fitSliceToBackground()

            # Link the node's together, so moving one moves the rest
            composite_node.SetLinkedControl(True)

            # Track the slice node for later
            self._slice_node_map[layout_name] = slice_node

        # Snap everything to IJK
        snap_all_to_ijk()

    ## XML Helpers ##
    def _build_viewer_entry(self, name: str, orientation: str, color: str):
        return f"""
        <item><view class="vtkMRMLSliceNode" singletontag="{name}">
            <property name="orientation" action="default">{orientation}</property>
            <property name="viewlabel" action="default">{name}</property>
            <property name="viewcolor" action="default">{color}</property>
        </view></item>
        """

    ## Memory Handling
    def clean(self):
        # Clear all slice nodes from the MRML scene
        for n in self._slice_node_map.values():
            slicer.mrmlScene.RemoveNode(n)


## Layout GUI ##
class OrientationButtonArrayWidget(ctk.ctkCollapsibleGroupBox):
    def __init__(self, title: str = _("Volume Layout"), parent: qt.QWidget = None):
        """
        Generate a new button array for managing which orientations
        should be displayed in Slicer for the current data unit.
        """
        super().__init__(parent)

        # Change the title to match the requested one
        self.setTitle(title)

        # Create a layout for everything
        layout = qt.QVBoxLayout()
        self.setLayout(layout)

        # Add a label denoting that this is the layout manager
        orientationLabel = qt.QLabel(_("Orientation"))
        layout.addWidget(orientationLabel)

        # Build our set of buttons
        self.buttonList: list[tuple[Orientation, qt.QPushButton]] = self._initOrientationButtons(layout)

        # The layout handler this is bound too, if any
        self._bound_handler: Optional[LayoutHandler] = None

    def _initOrientationButtons(self, layout: qt.QLayout) -> list[tuple[Orientation, qt.QPushButton]]:
        """
        Build the trio of toggle-able orientation buttons
        for this layout GUI.

        Tracks the buttons associated with each orientation
        in a map for later reference.
        """
        # Create a widget to bundle them all in
        panelWidget = qt.QWidget()
        panelLayout = qt.QHBoxLayout(panelWidget)

        # Remove widget padding, as it looks bad
        panelLayout.setContentsMargins(0, 0, 0, 0)

        # For each orientation, create a button
        buttonList = list()
        for o in Orientation.TRIO:
            # Build the widgets itself
            label = o.slicer_node_label()
            btn = qt.QPushButton(label)

            # Make it check-able
            btn.setCheckable(True)

            # Add a function to it
            btn.clicked.connect(
                lambda val, ori=o: self.setOrientationShown(ori, val)
            )

            # Add it to the panel
            panelLayout.addWidget(btn)

            # Track it for later
            buttonList.append((o, btn))

        # Add the panel widget to the GUI
        layout.addWidget(panelWidget)

        # Add a button which checks all the other buttons (all orientations)
        allButton = qt.QPushButton(_("ALL"))
        allButton.setToolTip(_(
            "Show all orientations simultaneously."
        ))

        # When the button is pressed, ensure all the orientation buttons get pressed
        def onAllPressed():
            # Update the layout
            self._bound_handler.orientation = Orientation.TRIO
            self._bound_handler.apply_layout()

            # Press each button
            for __, btn in buttonList:
                btn.blockSignals(True)
                btn.checked = True
                btn.blockSignals(False)
        allButton.clicked.connect(onAllPressed)

        # Add a button to transpose the layout
        transposeButton = qt.QPushButton(_("TRANSPOSE"))
        transposeButton.setToolTip(_(
            "Flip the view diagonally (volumes left-to-right -> top-to-bottom, "
            "and vice versa)"
        ))

        # When the button is pressed, flip the view along its diagonal
        def onTransposePressed():
            self.horizontal_volumes = not self.horizontal_volumes
            self._bound_handler.apply_layout()
        transposeButton.clicked.connect(onTransposePressed)

        # Add the buttons together, side-by-side
        buttonPanel = qt.QHBoxLayout()
        buttonPanel.addWidget(allButton)
        buttonPanel.addWidget(transposeButton)

        # Add that panel to the main layout
        layout.addLayout(buttonPanel)

        # Return the button map for later user
        return buttonList

    @property
    def current_orientation(self) -> Orientation:
        # If we don't have a bound handler, we don't have an orientation
        if not self._bound_handler:
            return None

        # Get the current orientation of the bound layout handler
        return self._bound_handler.orientation

    @current_orientation.setter
    def current_orientation(self, new_orientation: Orientation):
        # Update the handler's orientation
        self._bound_handler.orientation = new_orientation

        # Update our buttons to match
        for o, btn in self.buttonList:
            btn.checked = o in new_orientation

    @property
    def horizontal_volumes(self) -> bool:
        return self._bound_handler.horizontal_volumes

    @horizontal_volumes.setter
    def horizontal_volumes(self, new_val: bool):
        self._bound_handler.horizontal_volumes = new_val

    def changeLayoutHandler(
        self,
        new_handler: LayoutHandler,
        transfer_layout_settings: bool = True
    ):
        """
        Swap the layout handler that the widget should bind too

        :param new_handler: The new handler that should be used
        :param transfer_layout_settings: If True, the new handler's layout
            settings are changed to match the (current) handler's
            before we swap over. If False, the widget is synced to
            the new handler's settings instead, leaving its layout
            untouched.
        """
        # If this is the first layout we're receiving, OR the user doesn't want
        # layout settings transferred, update ourselves to match the new handler.
        if not (transfer_layout_settings and self._bound_handler is not None):
            for o, btn in self.buttonList:
                btn.blockSignals(True)
                btn.checked = o in new_handler.orientation
                btn.blockSignals(False)
        # Otherwise, update the new handler's orientation to match our own
        else:
            new_handler.match_layout_settings_with(self._bound_handler)

        # Track the new data handler
        self._bound_handler = new_handler

    def setOrientationShown(self, orientation: Orientation, val: bool):
        # Update the current orientation value
        if val:
            self.current_orientation = self.current_orientation | orientation
        else:
            self.current_orientation = self.current_orientation &~ orientation

        # Apply the new layout
        self._bound_handler.apply_layout()
