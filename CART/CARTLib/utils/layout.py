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

import slicer


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

    def as_slicer(self):
        return str(self).split('.')[1].capitalize()

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
    Orientation.COR: "Coronal"
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
def lookup_color(idx: int):
    """
    Get the RGB string from Slicer's default lookup table.

    Cached to avoid multiple string iterations lagging iteration in slower computers.
    """
    # Assert the index is valid (greater than 0)
    assert idx >= 0, "Cannot choose a color using a negative index!"

    # Get the lookup table from our color scheme
    colors = slicer.util.getNode("GenericColors")
    lookup_table = colors.GetLookupTable()

    # Get the RGB tuple from the lookup table
    rgb_tuple = tuple(
        [int(round(v * 255)) for v in lookup_table.GetTableValue(idx)[:-1]]
    )

    # Return its string representation
    return "#%0.2X%0.2X%0.2X" % rgb_tuple


## Viewer Layout Management ##
class LayoutHandler:
    def __init__(
        self,
        volume_nodes: list[slicer.vtkMRMLVolumeNode],
        orientation: Orientation = Orientation.AXIAL,
        horizontal_layout: bool = True
    ):
        """
        Layout handler which manages the viewers for a set of volume nodes for you.

        :param volume_nodes: The list of volume nodes this layout should manage our
            viewer layout for.
        :param orientation: The orientation(s) that the layout should account for.
        :param horizontal_layout: Whether the views for each volume node should be laid
            out horizontally (left-to-right). If false, they are displayed vertically
            (top-to-bottom) instead.
        """
        # Attributes
        self.volume_nodes = volume_nodes
        self.orientation = orientation
        self.horizontal_layout = horizontal_layout

        # Pseudo-cached XML layout; use `layout` instead
        self._layout: Optional[str] = None

        # Tracked map of view names -> volume and orientation tuples
        self._view_name_map: (
            Optional[dict[str, tuple[slicer.vtkMRMLVolumeNode, Orientation]]]
        ) = None

    ## Layout Handlers ##
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

    def rebuild_layout(self):
        # Determine how we will lay out our volumes (and each of their views)
        volume_layout = "horizontal" if self.horizontal_layout else "vertical"
        orient_layout = "vertical" if self.horizontal_layout else "horizontal"

        # Begin building the layout XML
        layout_xml = f'<layout type="{volume_layout}">'

        # Reset our volume name map, as we are about to rebuild it
        self._view_name_map = dict()

        # Keep track of a color index interator to update through these loops
        color_idx = 1
        for v in self.volume_nodes:
            # Add a sub-layout for each volume node's orientations
            layout_xml += f' <item> <layout type="{orient_layout}">\n'
            for o in self.orientation:
                # Set up our parameters to build the XML entry
                ori = o.as_slicer()
                name = f"{v.GetName()}--{ori}"
                color = lookup_color(color_idx)
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

        # TODO: Add background handling

        # Build up our slice nodes for each of the views we have in our layout.
        layout_manager = slicer.app.layoutManager()
        for l, (v, o) in self._view_name_map.items():
            # Grab the corresponding widget in our layout
            slice_widget = layout_manager.sliceWidget(l)

            # Ensure that only the volume node is shown in that widget
            # TODO: Implement a "shared back-ground" solution
            composite_node = slice_widget.mrmlSliceCompositeNode()
            composite_node.SetBackgroundVolumeID(v.GetID())
            composite_node.SetForegroundVolumeID("")

            # Get the slice node which manages the slice the widget views
            slice_node = slice_widget.mrmlSliceNode()

            # Ensure it matches its associated volume's orientation and rotation.
            slice_node.SetOrientation(o)
            slice_node.RotateToVolumePlane(v)
            slice_widget.fitSliceToBackground()

            # Link the node's together, so moving one moves the rest
            composite_node.SetLinkedControl(True)

        # Snap everything to IJK
        snap_all_to_ijk()

    def _invalidates_layout(func):
        """
        Decorator which denotes that the current layout ceases to be valid when the
        decorated function is called.
        """
        def wrapper(self, *args, **kwargs):
            self._layout = None
            func(self, *args, **kwargs)

        return wrapper

    ## Orientation Handling ##
    @_invalidates_layout
    def set_orientation(self, new_ori: Orientation):
        self.orientation = new_ori

    ## XML Helpers ##
    def _build_viewer_entry(self, name: str, orientation: str, color: str):
        return f"""
        <item><view class="vtkMRMLSliceNode" singletontag="{name}">
            <property name="orientation" action="default">{orientation}</property>
            <property name="viewlabel" action="default">{name}</property>
            <property name="viewcolor" action="default">{color}</property>
        </view></item>
        """
