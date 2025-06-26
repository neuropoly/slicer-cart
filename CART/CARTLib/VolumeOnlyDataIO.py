from DataUnitBase import DataUnitBase
import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *

class VolumeOnlyDataUnit(DataUnitBase, ScriptedLoadableModuleLogic):

    def __init__(
            self,
            initial_data: dict,
            base_path: str,
            scene: slicer.vtkMRMLScene | None = None,
    ):
        """
        Initialize the VolumeOnlyDataIO with optional initial data.

        Args:
            initial_data (dict, optional): Initial data to populate the instance.
        """
        super().__init__(
            data=initial_data,
            scene=scene
        )
        self.initial_data = initial_data if initial_data else {}
        self.resources = {}

        self.uid = self.initial_data.get("uid", None)
        self.validated = False
        if scene is None:
            scene = slicer.getMRMLScene()

    def _validate(self):
        """
        Validate the data in this instance.

        Raises:
            ValueError: If the data is invalid.
        """
        if not self.uid:
            raise ValueError(_("UID is required for VolumeOnlyDataIO."))

        key: str
        value: str
        for key, value in self.initial_data.items():
            if key == "uid":
                continue
            else:
                if not isinstance(value, str):
                    raise ValueError(
                        f"Invalid data for key '{key}': expected string, got {type(value).__name__}"
                    )
                if value == "":
                    raise ValueError(
                        f"Invalid data for key '{key}': value cannot be empty."
                    )
                if not value.endswith(".nrrd"):
                    raise ValueError(
                        f"Invalid data for key '{key}': value must be a .nrrd file."
                    )

        self.validated = True

    def _initialize_resources(self):
        """
        Initialize the resources for this VolumeOnlyDataIO instance.

        This method should be called after validation to set up the resources.
        """
        if not self.validated:
            raise ValueError(_("Data must be validated before initializing resources."))

        # Example of how to initialize resources, assuming the data is a file path
        for key, value in self.initial_data.items():
            if key != "uid":
                node = slicer.util.loadVolume(value)
                if node:
                    self.resources[key] = node
                else:
                    raise ValueError(f"Failed to load volume from {value}")



    def to_dict(self) -> dict:
        """
        Convert the data from the associated MRML nodes to a dictionary representation.

        Returns:
            dict: A dictionary representation of the data.
        """
        pass



