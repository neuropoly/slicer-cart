import logging
from abc import ABC, abstractmethod

from .DataUnitBase import DataUnitBase


class TaskBaseClass(ABC):
    """
    Base class for a task in the CART library.

    A "Task" is both the front-facing GUI component and the backend code interfaces between
    said GUI and a DataUnit instance.
    """

    def __init__(self, data_unit: DataUnitBase | None = None):
        """
        Basic constructor.

        This is functional on its own, but you will likely want to extend it in
        a subclass.
        """
        # Create a logger to track the goings-on of this task.
        self.logger = logging.getLogger(f"{__class__.__name__}")

        # Set the data unit to the one provided in the constructor, if any
        self.data_unit = data_unit

        # Build the front-end GUI for this task.
        self.gui = self.buildGUI()

        # If the task was specified, update the GUI with contents
        if self.data_unit:
            self.updateGUI(self.data_unit)


    @abstractmethod
    def buildGUI(self):
        """
        Build the GUI widget for this task.

        It will be rendered underneath the "main" iterator GUI.

        If you have "subtasks", we recommend using a collapsible frame
        (ctk.ctkCollapsibleFrame) to contain the relevant widgets.

        :return:
        """

        raise NotImplementedError("connectToGUI must be implemented in subclasses")


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

