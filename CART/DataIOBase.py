from abc import abstractmethod, ABC
import slicer

class DataIOBase(ABC):

    def __init__(self):
        """
        Initialize the DataIOBase instance.

        This constructor is intended to be called by subclasses to set up any necessary state.
        """
        super().__init__()


    @abstractmethod
    def to_dict(self) -> dict:
        """
        Convert the data from the associated mrml nodes to a dictionary representation.

        This should be implemented
        so that we can generate a dictionary representation of the DataIOBase instance.
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
    def get_data_uid(self) -> str:
        """
        Retrieve the unique identifier (UID) for this DataIOBase instance.

        Returns:
            str: The UID of the data.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")

    @abstractmethod
    def get_resources(self) -> dict[str, slicer.vtkMRMLNode]:
        """
        Retrieve the resources associated with this DataIOBase instance.

        Returns:
            dict[str, slicer.vtkMRMLNode]: A dictionary of resources.
        """
        raise NotImplementedError("This method must be implemented in subclasses.")


