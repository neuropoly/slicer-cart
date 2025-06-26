from abc import abstractmethod, ABC
from typing import Any

import slicer

class DataIOBase(ABC):

    def __init__(self, data: dict, scene: slicer.vtkMRMLScene):
        """
        Initialize the DataIOBase instance.

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
        Convert the data from the associated mrml nodes to a dictionary representation.

        This should be implemented
        so that we can generate a dictionary representation of the DataIOBase instance.

        For keeping the DataManger in sync with the saved output csv.
        """

        raise NotImplementedError("This method must be implemented in subclasses.")

    @abstractmethod
    def _validate(self):
        """
        Validate the data in this DataIOBase instance.

        This method should be implemented to ensure that the initial input data is valid.
        Raises:
            ValueError: If the data is invalid.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")

    @abstractmethod
    def _initialize_resources(self):
        """
        Initialize the resources for this DataIOBase instance.

        This method should be implemented to set up the resources after validation.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")

    @abstractmethod
    def get_resouces(self, key: str) -> Any:
        """
        Retrieve the resources associated with this DataIOBase instance.

        Returns:
            value associated with the given key in the resources dictionary.
            Most likely a vtkMRMLNode or similar object.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")


    def get_scene(self) -> slicer.vtkMRMLScene:
        """
        Retrieve the MRML scene associated with this DataIOBase instance.

        Returns:
            slicer.vtkMRMLScene: The MRML scene.
        """
        return self.scene


    def get_data_uid(self) -> str:
        """
        Retrieve the unique identifier (UID) for this DataIOBase instance.

        Returns:
            str: The UID of the data.
        """
        return self.uid
