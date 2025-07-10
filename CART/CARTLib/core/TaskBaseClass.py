import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, Optional, TypeVar, Protocol

import qt
import slicer
from .DataUnitBase import DataUnitBase

# Generic type hint class for anything which is a subclass of DataUnitBase
D = TypeVar('D', bound=DataUnitBase)


# Protocol signature which matches the DataUnitBase constructor; allows users to
#  return non-init functions if they have a different method they want to use
#  instead
class DataUnitFactory(Protocol):
    def __call__(
            self,
            case_data: dict[str, str],
            data_path: Path,
            scene: Optional[slicer.vtkMRMLScene] = None
    ) -> D:
        ...


class TaskBaseClass(ABC, Generic[D]):
    """
    Base class for a task in the CART library.

    A "Task" is both the front-facing GUI component and the backend code
    interfaces between said GUI and a DataUnit instance.

    You can specify a specific DataUnitBase (or set of them) in your subclass
    if you like through Python's Generic typing hints; this can help immensely
    with debugging, but (like all type hints) is not enforced by us or Python
    itself.!
    """

    def __init__(self, data_unit: Optional[D] = None):
        """
        Basic constructor.

        This is functional on its own, but you will likely want to extend it in
        a subclass.

        TODO: Swap Optional for newer Optional syntax ('D | None');
         currently only on Python 3.10 and up (which Slicer 5.8 doesn't have)
        """
        # Create a logger to track the goings-on of this task.
        self.logger = logging.getLogger(f"{__class__.__name__}")

        # Set the data unit to the one provided in the constructor, if any
        self.data_unit: D = data_unit

        # If the task was specified, update the GUI with contents
        if self.data_unit:
            # TODO: Validate that the DataUnit has all fields needed for this task.
            self.receive(self.data_unit)

    @abstractmethod
    def setup(self, container: qt.QWidget):
        """
        Build a GUI for this task. Very similar to
          `ScriptedLoadableModuleWidget.setup`, except you are placing
          everything into the passed "container" widget (rather than
          self.layout)

        The "container" widget is what will actually be rendered; it
          does not have a layout yet, so you will need to provide it yourself
          (using a QLayout subclass of your choice). Anything placed within
          the widget will be contained within the "Task Steps" dropdown.

        You should NOT pull data from a DataUnit at this time; just build the
          "default" version of the GUI here to avoid redundant calls. You should
          populate the GUI within the `setup` function below instead.
        """

        raise NotImplementedError("buildGUI must be implemented in subclasses")

    @abstractmethod
    def receive(self, data_unit: D):
        """
        Receive a new DataUnit instance.

        You should update your parameters here, be they managed by a
        ParameterNode or otherwise.

        This is run every time the case is changed, with the "new"
        case's contents being provided through `data_unit`.
        """

        raise NotImplementedError("setup must be implemented in subclasses")

    @abstractmethod
    def save(self) -> bool:
        """
        Run when the user requests the current data in the case be saved.

        Does what it says on the tin. This function should pull anything you
        need (i.e from an active GUI), format it, and save it where you like
        (including, potentially, the original cohort file).

        By default, this is also AUTOMATICALLY RUN when a new case is loaded.
        """

        raise NotImplementedError("save must be implemented in subclasses")

    def isTaskComplete(self, data_unit: D) -> bool:
        """
        Checks whether a DataUnit has been completed or not. How you choose to
        determine this is up to you (probably based on whether appropriate
        output exists).

        This is used for a number of functions, namely:
          * TODO: Starting at the first case the user has yet to complete
          * TODO: Skipping over already completed cases
          * TODO: Deciding whether to cache a case the user just moved past
        """
        return False

    def cleanup(self):
        """
        Called when the task is destroyed (Slicer was closed, a new task was loaded, etc.).

        Override to add any functionality you need to run to avoid memory leaks.

        Common things to do include:
          * Closing open I/O streams (i.e. files)
          * Removing objects from the Slicer MRML scene (i.e. a loaded segmentation)
          * Deleting large objects explicitly (i.e. large segmentations)
        """
        pass

    def getRequiredFields(self) -> Optional[list[str]]:
        """
        Provide a list of fields which need to be within each DataUnit for
        this task. For example, this could include field called "T2w MRI" field
        for a segmentation-like task; if the DataUnit does not have this in
        its contents, the task will not load it, skipping over it with a prompt
        instead.
        """
        return None

    @classmethod
    @abstractmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """
        Returns a factory map (in label -> factory form) which, when called,
        generates a new DataUnit instance of a type appropriate for use by this
        task.

        The "default" factory is just the class of your DataUnit subclass; for
         example:

        ```
        return {
            "Main": TaskDataUnit
        }
        ```

        If you have a factory method instead, you can return that:

        ```
        return {
            "Factory": TaskDataUnit.build_unit
        }
        ```

        Note the lack of a trailing '()' in both; we need the *functions* here,
         not their results!
        """

        raise NotImplementedError("setup must be implemented in subclasses")

    # TODO: Add standardized metadata which can be referenced by CART to
    #  build a task list.


# TODO: Remove, this is for reference only.
# class TaskBase(ABC):
#     """
#     Abstract base class for tasks that can be performed on cases.
#     # TODO Make this connect to TaskConfiguration so you initialize it with a TaskConfiguration instance.
#     """
#
#     def __init__(self, task_id: str, task_name: str, description: str = "") -> None:
#         self.task_id = task_id
#         self.task_name = task_name
#         self.description = description
#         self.logger = logging.getLogger(f"{__class__.__name__}.{task_id}")
#
#         self.is_active = False
#         self.metadata: dict[str, Any] = {}
#
#     @abstractmethod
#     def setup(self, case: DataUnitBase) -> bool:
#         ...
#
#     @abstractmethod
#     def execute(self, case: DataUnitBase) -> bool:
#         ...
#
#     @abstractmethod
#     def validate(self, case: DataUnitBase) -> bool:
#         ...
#
#     @abstractmethod
#     def cleanup(self, case: DataUnitBase) -> None:
#         ...
#
#     @abstractmethod
#     def save_results(self, case: DataUnitBase) -> bool:
#         ...
#
#     def get_required_nodes(self) -> list[str]:
#         return []
#
#     def get_task_metadata(self) -> dict[str, Any]:
#         return {
#             "task_id": self.task_id,
#             "task_name": self.task_name,
#             "description": self.description,
#             "is_active": self.is_active,
#             "required_nodes": self.get_required_nodes(),
#             "metadata": self.metadata,
#         }

