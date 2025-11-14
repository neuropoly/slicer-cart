import importlib.util
import inspect
import sys
from pathlib import Path

from CARTLib.core.TaskBaseClass import TaskBaseClass


CART_TASK_REGISTRY: dict[str, type[TaskBaseClass]] = dict()


def cart_task(label: str):
    """
    Class decorator for Tasks we want to register and make available to
    the user. In most cases, the decorated Task class will be registered
    immediately once the file containing it is imported for the first time.

    This initial import is usually done during CART initialization
    (see `initialize_tasks` below), but can be run post-init if needed;
    an example of this is the user selecting a new Task entrypoint through
    the GUI #TODO#
    """
    def _register_task(cls: type[TaskBaseClass]):
        # Otherwise, check if a task with this label already exists
        if label in CART_TASK_REGISTRY.keys():
            # If it does, it is possibly a redundant import;
            # Check if the source files match
            new_file_owner = Path(inspect.getfile(cls))
            prior_task = CART_TASK_REGISTRY.get(label)
            old_file_owner = Path(inspect.getfile(prior_task))

            # If they do, skip registration entirely, as it's redundant
            # KO: this can occur when one registered task inherits from another,
            #  with the former having already registered itself before the latter
            #  imports it again (likely in a new module space)
            if new_file_owner.resolve() == old_file_owner.resolve():
                return cls

            # Otherwise, we're trying to override and existing task; raise an error
            if not prior_task is cls:
                raise ValueError(f"Cannot register task '{label}'; task with the same "
                                 f"name has already been registered with CART.")

        # Then check that the task implements all functions we need it too
        elif not issubclass(cls, TaskBaseClass):
            raise ValueError(f"Cannot register task '{label}'; task is not a "
                             f"subclass of TaskBaseClass, providing necessary hookups.")

        # If nothing was problematic, add the clas to our registry
        CART_TASK_REGISTRY[label] = cls
        cls._registered_by_cart = True

        return cls

    return _register_task


def task_from_file(task_path: Path):
    # Validate the designated path is worth trying to import
    if not task_path.exists():
        raise ValueError(f"File '{task_path}' does not exist; cannot load task!")
    elif not task_path.is_file():
        raise ValueError(f"Path '{task_path}' is not a file; cannot load directories!")

    # Track the list of tasks already registered
    prior_tasks = set(CART_TASK_REGISTRY.keys())

    # Add the parent of the path to our Python path
    module_path = str(task_path.parent.resolve())
    sys.path.append(module_path)
    module_name = task_path.name.split('.')[0]

    try:
        # Try to load the module in question
        spec = importlib.util.spec_from_file_location(module_name, task_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        # If something went wrong, roll back our changes to `sys.path`
        sys.path.remove(module_path)
        raise e

    # Get the list of tasks added to the repo
    new_tasks = set(CART_TASK_REGISTRY.keys()) - prior_tasks

    # If no new tasks were registered, roll back the changes and raise an error
    if len(new_tasks) < 1:
        sys.path.remove(module_path)
        raise ValueError(f"No tasks were registered when imporeting the file '{task_path}'; "
                         f"Rolling back import.")

    # Otherwise, track it and return the new list for further processing
    sys.modules[module_name] = module
    return new_tasks


def initialize_tasks():
    # Start by loading our built-in (example) tasks
    examples_path = Path(__file__).parent.parent / "examples"
    segment_eval_task_path = examples_path / "SegmentationReview/SegmentationReviewTask.py"
    generic_classification_path = examples_path / "GenericClassification/GenericClassificationTask.py"
    rapid_markup_path = examples_path / "RapidMarkup/RapidMarkupTask.py"

    task_from_file(segment_eval_task_path)
    task_from_file(generic_classification_path)
    task_from_file(rapid_markup_path)
