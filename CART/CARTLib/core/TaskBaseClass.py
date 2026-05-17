import logging
from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

import qt
from slicer.i18n import tr as _

from CARTLib.core.DataUnitBase import DataUnitBase, DataUnitFactory
from CARTLib.utils.config import (
    JobProfileConfig,
    MasterProfileConfig,
    DictBackedConfig,
    ResourceSpecificConfig,
)

# Generic type hint class for anything which is a subclass of DataUnitBase
D = TypeVar("D", bound=DataUnitBase)


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

    def __init__(
        self,
        master_profile: MasterProfileConfig,
        job_profile: JobProfileConfig,
        cohort_features: list[str]
    ):
        """
        Basic constructor.

        This is functional on its own, but you will likely want to extend it in
        a subclass.
        """
        # Track the profile for later; we often want to stratify our task by
        # the profile that is running it.
        self.master_profile: MasterProfileConfig = master_profile
        self.job_profile: JobProfileConfig = job_profile
        self.cohort_features: list[str] = cohort_features

        # Create a logger to track the goings-on of this task.
        self.logger = logging.getLogger(f"{__class__.__name__}")

    ## Abstract Methods ##
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
          populate the GUI within the `receive` function below instead.
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
    def save(self) -> Optional[str]:
        """
        Run when the user requests the current data in the case be saved.

        Does what it says on the tin. This function should pull anything you
        need (i.e from an active GUI), format it, and save it where you like
        (including, potentially, the original cohort file).

        By default, this is also AUTOMATICALLY RUN when a new case is loaded.

        Returns None on a successful save; otherwise, return an error message
        describing what went wrong.
        """

        raise NotImplementedError("save must be implemented in subclasses")

    @classmethod
    @abstractmethod
    def getDataUnitFactory(cls) -> DataUnitFactory:
        """
        Get the data unit factory for this task.

        If in doubt, just return the class object, as it (should) matches the Protocol.
        """

        raise NotImplementedError("setup must be implemented in subclasses")

    ## Class Methods ##
    @classmethod
    def description(cls):
        """
        A description for this task, detailing what it should be used for, as well as
        anything else the user should know before they use it.

        Parsed as a Markdown file; images will not load, however!
        """
        return _(
            f"'{cls.__name__}' has no description; you should remind the developer to provide one!"
        )

    TaskConfig = TypeVar("TaskConfig", bound=DictBackedConfig)

    @classmethod
    def init_config(cls, job_config: JobProfileConfig) -> TaskConfig:
        """
        Initialize a config instance to manage configurable settings for a Task.

        If this returns None, or the resulting config does not re-implement the
        'generateGUILayout' function, the user will not be presented with
        any task-specific configuration options during job creation and/or
        cohort editing.
        """
        return None

    @classmethod
    def drop_resource_config(cls, resource_id: str, task_config: TaskConfig):
        """
        Remove any configuration options for the provided resource ID
        with the provided configuration.

        The configuration object will be of the same type as that created in
        `init_config` prior; use it as you see fit.
        """
        pass

    @classmethod
    def rename_resource_config(cls, old_id: str, new_id: str, task_config: TaskConfig):
        """
        Move the configuration options stored for one resource to another.
        """
        pass

    ## Instance Methods ##
    def save_on_iter(self) -> Optional[str]:
        """
        Called when the task is asked to save due to the case being changed.

        By default, just saves as normal; overwrite if you want some custom
        functionality to be run in this context.

        Returns None on a successful save; otherwise, return an error message
        describing what went wrong.
        """
        print("Saving...")
        save_result = self.save()
        if not save_result:
            print("Iteration save was successful!")
        else:
            raise ValueError(f"An error occurred during saving: {save_result}")

    def generate_prior_data_for(self, case_data: dict) -> Optional[dict]:
        """
        Return a dictionary containing data required to re-load previous
        outputs for a case.

        This is ONLY run when all the following conditions are met:
          * CART is configured by the user to load previous outputs.
          * The case in question was marked as being previously run by the active task.
          * The case is not already loaded (being actively used or in cache).

        The resulting dictionary is then passed to the active data unit
        factory, and can be used to change how the resulting data unit
        is constructed. See DataUnitBase:__init__ for further details.
        """
        return None

    def isTaskComplete(self, case_data: dict[str, str]) -> Optional[bool]:
        """
        Checks whether a case has been completed or not. How you choose to
        determine this is up to you (probably based on whether appropriate
        output exists). Should return None if unsure (the default).

        This is used for a number of functions, namely:
          * Starting at the first case the user has yet to complete
          * Skipping over already completed cases
        """
        return None

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

    def enter(self):
        """
        Called when the CART module is loaded; you should ensure any
        GUI elements attached to this task are synchronized and ready to be
        used again here. For example:

        * Synchronize any widgets which rely on the MRML state
        * Re-initialize keyboard shortcuts
        * Restart a timer

        This is also called once when a task is first initialized to simulate
        CART being loaded! Be careful to avoid redundant calls!
        """
        pass

    def exit(self):
        """
        Called when the CART module is unloaded, and any associated GUI hidden;
        You should ensure that nothing is running in the background while the
        other module is being used to avoid user confusion.

        Some things that you might to do to prevent this include:

        * Pause a running timer
        * Unlink anything dependent on the MRML state that you don't want to
         implicitly synchronize
        * Disable keyboard shortcuts

        You probably don't want to delete anything at this point, as the user
        might bring it back into focus later! Instead, place anything that needs
        to be handled when CART and/or the task is terminated into `cleanup`;
        `exit` is called right before most `cleanup` calls anyway.
        """
        pass


class CARTTask(TaskBaseClass, ABC, Generic[D]):
    """
    Unique subclass which provided default implementations for resource-specific config
    options, to match those used by CART's default resource types.
    """

    @classmethod
    def drop_resource_config(
        cls, resource_id: str, task_config: TaskBaseClass.TaskConfig
    ):
        # Use our resource-specific config manager to ensure standardization
        resource_config = ResourceSpecificConfig(task_config)
        resource_config.drop_resource_config(resource_id)

    @classmethod
    def rename_resource_config(
        cls, old_id: str, new_id: str, task_config: TaskBaseClass.TaskConfig
    ):
        # Use our resource-specific config manager to ensure standardization
        resource_config = ResourceSpecificConfig(task_config)
        resource_config.rename_resource(old_id, new_id)
