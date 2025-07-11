from pathlib import Path
from typing import Optional

import slicer
from ..core.DataUnitBase import DataUnitBase
from slicer.i18n import tr as _


class SegmentationEvaluationDataUnit(DataUnitBase):
    ## CASE_KEYS ##
    VOLUME_KEY = "volume"
    SEGMENTATION_KEY = "segmentation"
    COMPLETED_KEY = "completed"

    def __init__(
            self,
            case_data: dict[str, str],
            data_path: Path,
            scene: Optional[slicer.vtkMRMLScene] = slicer.mrmlScene
    ):
        super().__init__(case_data, data_path, scene)

        # Track the volume and segmentation nodes
        self.volume_node = None
        self.segmentation_node = None

        # Hierarchy node which manages subjects, for ease of access
        self.hierarchy_node = None

        # Subject ID for nodes associated with this data unit
        self.subject_id: int = None

        # Track whether this node has been processed already or not
        self.is_complete = case_data.get(self.COMPLETED_KEY, False)

        # Initialize our resources
        self._initialize_resources()

    def to_dict(self) -> dict:
        return {
            self.VOLUME_KEY: self.case_data[self.VOLUME_KEY],
            self.SEGMENTATION_KEY: self.case_data[self.SEGMENTATION_KEY],
            self.COMPLETED_KEY: self.is_complete
        }

    def focus_gained(self):
        # Make our managed nodes visible again
        self.volume_node.SetDisplayVisibility(True)
        self.segmentation_node.SetDisplayVisibility(True)

        # Expand the subject hierarchy and make it visible
        self.hierarchy_node.SetItemExpanded(self.subject_id, True)
        self.hierarchy_node.SetItemDisplayVisibility(self.subject_id, True)

    def focus_lost(self):
        # Make our managed nodes hidden again
        self.volume_node.SetDisplayVisibility(False)
        self.segmentation_node.SetDisplayVisibility(False)

        # Collapse the subject hierarchy and hide it
        # KO: This doesn't actually work, but the devs insist it does/will, so
        #  I'm keeping it here just in case it ever does
        self.hierarchy_node.SetItemExpanded(self.subject_id, False)
        self.hierarchy_node.SetItemDisplayVisibility(self.subject_id, False)

    def clean(self):
        # Un-focus the contents first, avoiding some potential UI bugs
        super().clean()
        # Remove the subject (and, by extension, all its children)
        self.hierarchy_node.RemoveItem(self.subject_id)

    def _validate(self):
        # Confirm that both a "volume" and "segmentation" entry exit
        self.validate_key_is_file(self.VOLUME_KEY)
        self.validate_key_is_file(self.SEGMENTATION_KEY)

        self.validated = True

    def validate_key_is_file(self, key: str):
        """
        Validate a file we need designed by our case:
          * Has been designated in the case
          * Exists
          * Is a valid file
        """
        # Check that there is an entry matching this key in the case
        file_path = self.case_data.get(key, None)
        if not file_path:
            raise ValueError(
                f"Case {self.uid} was missing required entry '{key}'."
            )

        # Confirm that something matching the designated path exists on our drive
        file_path = self.data_path / file_path
        if not file_path.exists():
            raise ValueError(
                f"Path for '{key}' does not exist for case {self.uid}."
            )

        # Confirm that it is a file
        if not file_path.is_file():
            raise ValueError(
                f"Path for '{key}' for case {self.uid} was not a file."
            )

    def _initialize_resources(self):
        """
        Attempt to load the volume and segmentation files into memory as
         MRML nodes.
        """
        if not self.validated:
            raise ValueError(_("Data must be validated before initializing resources."))

        # Initialize the nodes containing our actual data
        vn = self._init_volume_node()
        sn = self._init_segmentation_node()

        # Ensure the segmentation node aligns with the geometry of the volume
        self.segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(
            self.volume_node
        )

        # Initialize a subject to hold everything in for management sakes
        self._init_subject([sn, vn])

    def _init_volume_node(self):
        # Load the volume node first
        volume_path = self.data_path / self.case_data[self.VOLUME_KEY]
        self.volume_node = slicer.util.loadVolume(volume_path, {"show": False})

        # Update it and add it to our resources for easy access elsewhere
        self.volume_node.SetName(self.VOLUME_KEY)
        self.resources[self.VOLUME_KEY] = self.volume_node

        return self.volume_node

    def _init_segmentation_node(self):
        # Load the segmentation as a labelled volume first
        segmentation_path = self.data_path / self.case_data[self.SEGMENTATION_KEY]
        label_node = slicer.util.loadLabelVolume(segmentation_path)

        # Then create our segmentation node
        self.segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        self.segmentation_node.SetName(self.SEGMENTATION_KEY)

        # And pack the label node into the segmentation node; this auto-handles
        #  color coding for us
        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
            label_node, self.segmentation_node
        )

        # Remove the (now redundant) label node from the scene
        self.scene.RemoveNode(label_node)

        return self.segmentation_node

    def _init_subject(self, node_list: list):
        # Place them into a subject hierarchy for organization
        shNode = self.scene.GetSubjectHierarchyNode()
        self.subject_id = shNode.CreateSubjectItem(
            shNode.GetSceneItemID(),
            self.uid
        )
        for n in node_list:
            print(hex(hash(n)))
            item_id = shNode.GetItemByDataNode(n)
            shNode.SetItemParent(item_id, self.subject_id)

        self.hierarchy_node = shNode
