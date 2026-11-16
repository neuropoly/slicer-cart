from pathlib import Path

import slicer

from CARTLib.utils.data import CARTStandardUnit


class ClassificationUnit(CARTStandardUnit):
    """
    A data unit for the Generic Classification task.

    Manages the volumes, segmentations, and markups associated with a given case,
    as well as the current classification of the case (if any).
    """
    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        prior_data: dict = None,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ):
        super().__init__(case_data, data_path, prior_data, scene)

        # Current classifications for this case
        if prior_data is None:
            prior_data = {}
        self.classes: set[str] = prior_data.get("classes", set())
        self.remarks: str = prior_data.get("remarks", "")

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
        self.classes.add(new_class)

    def drop_class(self, drop_class: str):
        if drop_class not in self.classes:
            print(f"WARNING: Case was not class '{drop_class}' already, not removed.")
            return
        self.classes.remove(drop_class)