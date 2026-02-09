import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, Optional, TypeVar, Protocol

import qt
import slicer
from slicer.i18n import tr as _

from CARTLib.core.DataUnitBase import DataUnitBase
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig

# Generic type hint class for anything which is a subclass of DataUnitBase
D = TypeVar("D", bound=DataUnitBase)


# Protocol signature which matches the DataUnitBase constructor; allows users to
#  return non-init functions if they have a different method they want to use
#  instead
class DataUnitFactory(Protocol):
    def __call__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: Optional[slicer.vtkMRMLScene] = None,
    ) -> D: ...


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
        self, master_profile: MasterProfileConfig, job_profile: JobProfileConfig
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

        # Create a logger to track the goings-on of this task.
        self.logger = logging.getLogger(f"{__class__.__name__}")

    # Aliases for commonly accessed attributes
    @property
    def profile_label(self) -> str:
        return self.job_profile.label

    @property
    def profile_role(self) -> str:
        return self.job_profile.role

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
    def description(cls):
        """
        A description for this task, detailing what it should be used for, as well as
        anything else the user should know before they use it.
        """
        return _(
            f"'{cls.__name__}' has no description; you should remind the developer to provide one!"
        )

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

    def isTaskComplete(self, case_data: dict[str:str]) -> bool:
        """
        Checks whether a case has been completed or not. How you choose to
        determine this is up to you (probably based on whether appropriate
        output exists).

        This is used for a number of functions, namely:
          * Starting at the first case the user has yet to complete
          * Skipping over already completed cases
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

    @classmethod
    def feature_types(cls, data_factory_label: str) -> dict[str, str]:
        """
        Provides a map containing a feature type label and its description
        for a "class" of feature this task can handle for the given data factory.
        `data_factory_label` will always be a value defined in `getDataUnitFactories`
        above.

        For example, if the given data unit factory can handle anatomical
        volume files and segmentation labels, you might return the following:

        ```
        {
            "Volume": "An anatomical volume you want to view. Must have 'volume' in its name.",
            "Segmentation: "A segmentation label to overlay on viewed volumes. Must have 'segmentation' in its name"
        }
        ```

        These are shown to the user during cohort creation, and used in conjunction
        with `feature_label_for` below to ensure each cohort feature will abide by
        the format required for this task when using the selected Data Unit Factory.

        By default, this returns an empty dictionary; if CART sees this, it will not
        provide ANY support to the user during cohort generation, likely result in
        cohort files which are malformed and/or misleading.
        """
        return {}

    @classmethod
    def format_feature_label_for_type(
        cls, initial_label: str, data_unit_factory_type: str, feature_type: str
    ):
        """
        Should reformat the "initial" label provided to be recognized as the
        specified feature type when provided to the specified data unit factory.

        The data unit type will always be one specified by `getDataUnitFactories`,
        and the feature type will always be one specified by `feature_types` for
        said data unit factory.

        For example, if we use the following feature types for `feature_types` prior:

        ```
        {
            "Volume": "An anatomical volume you want to view. Must have 'volume' in its name.",
            "Segmentation: "A segmentation label to overlay on viewed volumes. Must have 'segmentataion' in its name"
        }
        ```

        An initial label of "T2w" for a "Volume" type could be returned as "volume_T2w";
        if it were a "Segmentation" type instead, it could be "segmentation_T2w" instead.

        If this is not overridden in a subclass, only the bare-minimum processing
        (replacing commas with underscores) is applied.
        """
        return initial_label.replace(",", "_")
