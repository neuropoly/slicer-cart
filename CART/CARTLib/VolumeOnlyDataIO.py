from pathlib import Path
from typing import Optional

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _

from .core.DataUnitBase import DataUnitBase


class VolumeOnlyDataUnit(DataUnitBase, ScriptedLoadableModuleLogic):

    def __init__(
        self,
        case_data: dict,
        data_path: Path,
        # TMP: Until 5.9 (w/ Python 3.10+ support) is released, Optional is needed
        scene: Optional[slicer.vtkMRMLScene] = slicer.mrmlScene,
    ):
        """
        Initialize the VolumeOnlyDataIO with optional initial data.

        Args:
            case_data (dict, optional): Initial data to populate the instance.
        """
        self.base_path = data_path
        print(data_path)
        super().__init__(case_data=case_data, data_path=data_path)
        self.scene = scene
        self._initialize_resources()

    def _validate(self):
        """
        Validate the data in this instance.

        Raises:
            ValueError: If the data is invalid.
        """
        if not self.uid:
            raise ValueError(_("UID is required for VolumeOnlyDataIO."))

        key: str
        value: str | Path
        for key, value in self.case_data.items():
            if key == "uid":
                continue
            else:
                file_path = self._parse_path(value)
                if not file_path.exists():
                    raise ValueError(
                        f"Invalid data for key '{key}': file does not exist at {value}."
                    )

                if not file_path.name.endswith(".nrrd"):
                    raise ValueError(
                        f"Invalid data for key '{key}': value must be a .nrrd file."
                    )

    def _parse_path(self, path_str: str):
        # TODO: Make this reference a user-specified value instead
        if self.base_path is None:
            return Path(path_str)
        elif not isinstance(self.base_path, Path):
            raise ValueError(_("Base path must be a Path object."))
        elif not self.base_path.is_dir() or not self.base_path.exists():
            raise ValueError(_("Base path is not a valid directory."))
        else:
            return self.base_path / path_str

    def _initialize_resources(self):
        """
        Initialize the resources for this VolumeOnlyDataIO instance.

        This method should be called after validation to set up the resources.
        """
        if not self.validated:
            raise ValueError(_("Data must be validated before initializing resources."))

        # Example of how to initialize resources, assuming the data is a file path
        for key, value in self.case_data.items():
            if key != "uid":
                file_path = self._parse_path(value)
                node = slicer.util.loadVolume(file_path, {"show": False})
                if node:
                    # Track the volume for later
                    print(
                        f"Loaded volume from {file_path} into node {node.GetName()} with {hash(node)}"
                    )
                    node_name = f"{hash(self)}_{key}"
                    node.SetName(node_name)
                    self.resources[key] = node
                else:
                    raise ValueError(f"Failed to load volume from {value}")

    def to_dict(self) -> dict:
        """
        Convert the data from the associated MRML nodes to a dictionary representation.

        Returns:
            dict: A dictionary representation of the data.
        """
        # THIS IS NOT A COMMMON USE CASE, BUT BC THERE IS NO DATA IN THE MRML SCENE ONLY FILES WE ARE GOOD
        return self.case_data

    def focus_gained(self):
        # Reveal any currently invisible nodes
        self._show_all_nodes()
        print(f"{hash(self)} gained focus!")

    def focus_lost(self):
        # Reveal any currently invisible nodes
        self._hide_all_nodes()
        print(f"{hash(self)} lost focus!")

    def _show_all_nodes(self):
        """
        Make all nodes in this dataset visible when it gains focus

        TODO: Look into a way to reveal the nodes to the Data hierarchy as well
        """
        for n in self.resources.values():
            n.SetDisplayVisibility(True)

    def _hide_all_nodes(self):
        """
        Make all nodes in this dataset hidden when it loses focus

        TODO: Look into a way to hide the nodes from the Data hierarchy as well
        """
        for n in self.resources.values():
            n.SetDisplayVisibility(False)

    def clean(self):
        """
        Remove the nodes from the scene before deletion.

        As this object is also about to be deleted, no remaining references to
         the node should exist, and it will be safely cleaned by the garbage
         collector on its next pass!
        """
        # Un-focus the contents first, avoiding some potential UI bugs
        super().clean()
        # Remove each node from the scene, allowing it to fall out of memory
        for n in self.resources.values():
            self.scene.RemoveNode(n)
