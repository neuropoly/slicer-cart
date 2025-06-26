from abc import abstractmethod, ABC
from typing import Any

import slicer

class DataUnitBase(ABC):

    def __init__(self, data: dict, scene: slicer.vtkMRMLScene):
        """
        Initialize the DataUnit instance.

        This constructor is intended to be called by subclasses to set up any necessary state.

        # Inputs:
            - Dict from data manager with the following keys
                - uid: Unique identifier for the data.
                - * : Any additional keys that are relevant to the data and dictate a DataUnit Representation.
            - MRML Scene: The MRML scene to which this data will be added.
        # Outputs:
            - Updated DataUnit Representation AFTER the Task is complete/ user hit "next" button.
        """
        self.data = data
        self.scene = scene
        self.resources = {}
        self.uid = data.get("uid", None)
        self.validated = False
        self._validate()

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
    def _validate(self):
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
