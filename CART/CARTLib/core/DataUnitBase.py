from abc import abstractmethod, ABC
from pathlib import Path
from typing import Any, Optional

import slicer


class DataUnitBase(ABC):

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,  # Scene is NOT optional.
        # Default scene is the global MRML scene, which is always available.
    ):
        """
        Initialize a new data unit; you may want to add additional processing in
          subclasses.

        :param case_data: The contents of the cohort file for this specific case.
          Will always contain an "uid" entry; everything else is free-form
        :param data_path: A data path. Should be treated as the "working"
          directory for anything that needs to read from files on the disk.
        :param scene: A MRML scene, where nodes should be inserted into and
          managed within when the unit is in focus (actively being worked on)

        """
        # Tracking parameters
        self.data_path: Path = data_path
        self.case_data: dict[str, str] = case_data
        self.scene: slicer.vtkMRMLScene = scene

        # Resource tracking
        self.resources = {}
        self.uid = case_data.get("uid", None)

    @abstractmethod
    def to_dict(self) -> dict:
        """
        Export the data into the same format used to create a new DataUnit, ready
        to be saved to the cohort CSV.

        If you use this dictionary to create a new DataUnitBase instance, it should
        yield a DataUnitBase instance which is identical to this one.

        Used by the DataManger to keep the saved output csv in sync.
        """

        raise NotImplementedError("This method must be implemented in subclasses.")

    @abstractmethod
    def focus_gained(self):
        """
        This is called when the DataUnit is made the "focus" of the task. You should
         "reveal" any resources you are managing here by adding them back to the MRML
         scene.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")

    @abstractmethod
    def focus_lost(self):
        """
        This is called when the DataUnit is removed from the "focus" of the task. You
         should "hide" any resources you are managing here by removing them from the MRML
         scene.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")

    @abstractmethod
    def clean(self):
        """
        This method is called right before the DataUnit is deleted (due to the module
         closing, the unit falling out of cache, or Slicer closing).

        You should ensure any data managed in this data unit is removed from memory.
         Our "base" implementation attempts to do this by replicating the DataUnit
         "losing focus", but it is near certain you will need to extend this
         functionality.
        """
        self.focus_lost()

    @abstractmethod
    def validate(self):
        """
        Validate the data in this DataUnitBase instance.

        This method should be implemented to ensure that the initial input data is valid.
        Raises:
            ValueError: If the data is invalid.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")

    @abstractmethod
    def _initialize_resources(self):
        """
        Initialize the resources for this DataIOBase instance.

        This should take the contents of a (validated) data dictionary and create the
        associated resources in the MRML scene.

        This method should be implemented to set up the resources after validation.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")

    def get_resource(self, key: str) -> Any:
        """
        Retrieve a specified resource associated with this DataUnitBase instance.

        A resource can be any data that should be managed on a unit-by-unit basis,
        as it is presented within Slicer/Python.
        This is how your Task implementation should access data for display or processing.

        By default, this uses a backing dictionary, but you can override this in a subclass

        Generally, the return type should be a Slicer Node, but this is not enforced.

        """
        if key in self.resources:
            return self.resources[key]
        else:
            raise KeyError(f"Resource '{key}' not found in VolumeOnlyDataUnit.")

    def get_scene(self) -> slicer.vtkMRMLScene:
        """
        Retrieve the MRML scene associated with this DataIOBase instance.

        This scene contains the data unit's contents in Slicer's 'Node' format;
        it is cached to allow for quick access without needing to re-fetch it.

        Returns:
            slicer.vtkMRMLScene: The MRML scene.
        """
        return self.scene

    def get_data_uid(self) -> str:
        """
        Retrieve the unique identifier (UID) for this DataUnit instance.

        Returns:
            str: The UID of the data.
        """
        return self.uid

    def __del__(self):
        # When the object is garbage collected, run cleaning first
        self.clean()

    def __delete__(self, instance):
        # When the objecte is explicitly deleted, run cleaning first
        self.clean()
