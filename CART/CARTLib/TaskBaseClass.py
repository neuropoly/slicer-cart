import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar

from .DataUnitBase import DataUnitBase

# Generic type hint class for anything which is a subclass of DataUnitBase
D = TypeVar('D', bound=DataUnitBase)


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

        # Build the front-end GUI for this task.
        self.gui = self.buildGUI()

        # If the task was specified, update the GUI with contents
        if self.data_unit:
            # TODO: Validate that the DataUnit has all fields needed for this task.
            self.setup(self.data_unit)

    @abstractmethod
    def buildGUI(self):
        """
        Build the GUI widget for this task.

        It will be rendered underneath the "main" iterator GUI.

        If you have "subtasks", we recommend using a collapsible frame
        (ctk.ctkCollapsibleFrame) to contain the relevant widgets.

        You should NOT pull data from the DataUnit at this time; leave that
        to updateGUI to ensure everything stays synchronized.
        """

        raise NotImplementedError("buildGUI must be implemented in subclasses")

    @abstractmethod
    def setup(self, data_unit: D):
        """
        Update the contents of the GUI using the contents of a DataUnit.

        What elements of the DataUnit, how they should be displayed, and how
        you want to update Slicer's view should be dictated here.

        This is called when the DataManager requests this Task to load a new
        case; instead of re-drawing the GUI every time, update its existing
        widgets instead.
        """

        raise NotImplementedError("setup must be implemented in subclasses")

    @abstractmethod
    def save(self) -> bool:
        """
        Run when the user requests the current data in the case be saved.

        Does what it says on the tin. This function should pull anything you
        need out of the GUI, format it, and save it where you like (including,
        potentially, the original Cohort).

        By default, this is also AUTOMATICALLY RUN when you swap cases (click
        either the 'next' or 'previous' buttons).
        """

        raise NotImplementedError("save must be implemented in subclasses")

    def isTaskComplete(self, data_unit: D) -> bool:
        """
        Checks whether a DataUnit has been completed or not. How you choose to
        determine this is up to you (probably based on whether appropriate
        output exists). This is used to allow the user to "resume" where they
        left off, should they only complete the task for some of the cases in
        the cohort, but not all.

        If all tasks are complete, it starts at the beggining again.
        """
        return False

    def cleanup(self):
        """
        Called when the task is destroyed (Slicer was closed).

        Override to add any functionality you need to run to avoid memory leaks,
        close open I/O streams, etc.
        """
        pass

    def getRequiredFields(self) -> Optional[list[str]]:
        """
        Provide a list of fields which need to be within each DataUnit for
        this task. For example, this could include field called "T2w MRI" field
        for a segmentation-like task; if the DataUnit does not have this in
        its contents, the task will not load it, skipping over it with a prompt
        instead.

        TODO: Implement said prompt.
        """
        return None

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

