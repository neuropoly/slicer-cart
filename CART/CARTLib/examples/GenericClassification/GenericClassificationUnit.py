from pathlib import Path

import slicer

from CARTLib.utils.data import CARTStandardUnit


class GenericClassificationUnit(CARTStandardUnit):
    """
    A data unit for the Generic Classification task.

    Manages the volumes, segmentations, and markups associated with a given case,
    as well as the current classification of the case (if any).
    """
    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ):
        super().__init__(case_data, data_path, scene)

        # Current classifications for this case
        self._classes: set[str] = set()

        # Other remarks for this case
        self.remarks: str = ""

    @property
    def classes(self):
        return self._classes

    def toggle_class(self, label: str, new_state: bool):
        """
        "Toggles" the presence of the class in this data unit.

        Convenience wrapper for adding/removing a class from the toggle.
        """
        if new_state:
            self.add_class(label)
        else:
            self.drop_class(label)

    def add_class(self, new_class: str):
        if new_class in self.classes:
            print(f"WARNING: Class '{new_class}' was already registered!")
        self._classes.add(new_class)

    def drop_class(self, drop_class: str):
        if drop_class not in self._classes:
            print(f"WARNING: Case was not class '{drop_class}' already, not removed.")
            return
        self._classes.remove(drop_class)