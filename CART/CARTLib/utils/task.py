import inspect
from pathlib import Path
from typing import Optional

from CARTLib.core.TaskBaseClass import TaskBaseClass

"""
Registry for loaded CART tasks

If a task entry is "None", it indicates that a task by that name was
registered in the configuration, but the associated file did not exist
or was otherwise unavailable.
"""
CART_TASK_REGISTRY: dict[str, Optional[type[TaskBaseClass]]] = dict()


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
