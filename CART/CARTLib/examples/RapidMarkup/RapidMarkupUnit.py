from pathlib import Path

import slicer
from CARTLib.utils.data import CARTStandardUnit


class RapidMarkupUnit(CARTStandardUnit):

    MARKUP_KEY = "cart_markups"

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ) -> None:
        super().__init__(case_data, data_path, scene)

        # An annotation node in which the point list will be
        node_annotation_name = f"{self.uid}_{self.MARKUP_KEY}"
        self.markup_node = scene.AddNewNodeByClass(
            'vtkMRMLMarkupsFiducialNode',
            node_annotation_name
        )

        # Make our subject the "parent" of this node
        shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
        annotID = shNode.GetItemByDataNode(self.markup_node)
        shNode.SetItemParent(annotID, self.subject_id)

        # Add it to our list of markup nodes
        self.markup_keys.append(node_annotation_name)
        self.markup_nodes[node_annotation_name] = self.markup_node
