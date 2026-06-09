import copy
import csv
import json
import logging
import os
from collections import namedtuple
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Protocol, TYPE_CHECKING

import numpy as np
from numpy import typing as npt

import ctk
import qt
from slicer.i18n import tr as _

from .config import DictBackedConfig
from .widgets import (
    CSVBackedTableModel,
    CSVBackedTableWidget,
    CARTPathLineEdit,
    ChangeTrackingDialogue,
)

## Type Utils ##
if TYPE_CHECKING:
    # Avoid potential cyclic imports
    from CARTLib.core.TaskBaseClass import TaskBaseClass
    from CARTLib.core.DataUnitBase import ResourceType

    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt

# Typing aliases for commonly used dictionary mappings
CaseMap = dict[str, list[Path]]
FilterMap = dict[str, dict]
NameMap = dict[str, str]

# Current version of the cohort manager
COHORT_VERSION = "0.2.0"


## Core ##
# Named tuple to keep the resource-specific filters organized
ResourceFilter = namedtuple(
    "FilterEntry",
    ["original_name", "resource_type", "include", "exclude", "extension"],
    defaults=[""]*5  # Just default to empty strings for each if not provided.
)

class CohortModel(CSVBackedTableModel):
    """
    More specialized version of the CSV-backed model w/ additional checks
    and resources specific to cohort editing.
    """

    ## Constructors ##
    def __init__(
        self,
        # NOTE: These are "optional mandatory" to force devs to consider why they're doing this!
        csv_path: Optional[Path],
        data_path: Optional[Path],
        editable: bool = True,
        reference_task: "type[TaskBaseClass]" = None,
        use_sidecar: bool = True,
        parent: qt.QObject = None
    ):
        """
        Constructor

        :param csv_path: The file this model should save to (and load from, if it already exists).
        :param data_path: Where this cohort should look when trying to find resource files.
        :param editable: Whether this cohort can be edited by its views.
        :param reference_task: A task type this cohort should reference when generating "pretty" columns.
        :param use_sidecar: Whether to generator (and reference, if it already exists) a JSON sidecar file.
            If false, the cohort's resource and case maps will NOT be preserved across loads!
        :param parent: The parent widget for QT hierarchy management.
        """
        # Disable editing explicitly if no data path is provided
        if data_path is None:
            editable = False

        # Track the data path and reference task for later
        self._data_path = data_path
        self.reference_task = reference_task

        # Initialize blank placeholders
        self._case_map = dict()
        self._resource_map: dict[str, ResourceFilter] = dict()

        # Track whether to user a sidecar before initializing (which will attempt to load it)
        self.use_sidecar = use_sidecar

        super().__init__(csv_path, editable, parent)

        # Try to move the UID column to the front of the array
        if self._csv_path is not None:
            if not self._move_uid_to_index():
                raise ValueError("No UID column found, cannot set up Cohort model!")

        # Track whenever anything about this model changes!
        self.connectChangeEvents()

        # Set ourselves to "not changed"
        self.has_changed = False

    def connectChangeEvents(self):
        self.dataChanged.connect(self._mark_changed)
        self.headerDataChanged.connect(self._mark_changed)
        self.rowsInserted.connect(self._mark_changed)
        self.rowsMoved.connect(self._mark_changed)
        self.rowsRemoved.connect(self._mark_changed)
        self.columnsInserted.connect(self._mark_changed)
        self.columnsMoved.connect(self._mark_changed)
        self.columnsRemoved.connect(self._mark_changed)

    def disconnectChangeEvents(self):
        self.dataChanged.disconnect(self._mark_changed)
        self.headerDataChanged.disconnect(self._mark_changed)
        self.rowsInserted.disconnect(self._mark_changed)
        self.rowsMoved.disconnect(self._mark_changed)
        self.rowsRemoved.disconnect(self._mark_changed)
        self.columnsInserted.disconnect(self._mark_changed)
        self.columnsMoved.disconnect(self._mark_changed)
        self.columnsRemoved.disconnect(self._mark_changed)

    @classmethod
    def from_case_map(
        cls,
        csv_path: Path,
        data_path: Path,
        case_map: CaseMap,
        editable: bool = True,
        reference_task: "TaskBaseClass" = None,
        use_sidecar: bool = True
    ):
        # Generate the backing CSV immediately using the case map's contents
        row_data = [["uid"], *[[k] for k in case_map.keys()]]
        with open(csv_path, "w") as fp:
            csv.writer(fp).writerows(row_data)
        # Generate a new cohort instance, backed by this new CSV file and w/ a blank side-car
        cohort = cls(csv_path, data_path, editable, reference_task, False)
        cohort.use_sidecar = use_sidecar
        # Manually update its case map to match
        cohort._case_map = case_map
        # If we're using a sidecar, save its contents as well
        if use_sidecar:
            cohort._save_sidecar()

        return cohort

    ## Setup Utilities ##
    def _mark_changed(self):
        self.has_changed = True

    def _move_uid_to_index(self) -> bool:
        # If the UID is already in the index position, do nothing
        if self._csv_data[0, 0].lower() == "uid":
            return True
        # Otherwise, find and move the UID column to the front
        for i, c in enumerate(self.header):
            if c.lower() == "uid":
                # Model "reset", as this changes more than just one column's pos
                self.beginResetModel()
                uid_arr = self._csv_data[:, i]
                np.delete(self._csv_data, i, axis=1)
                np.insert(self._csv_data, 0, uid_arr, axis=1)
                self.endResetModel()
                return True
        # If that fails (there's no UID column), return False for handling
        return False

    ## Attributes/Properties ##
    @property
    def sidecar_path(self) -> Path:
        # Get-only to avoid desync
        return self.csv_path.with_suffix(".json")

    @property
    def case_map(self):
        # Get only; use the set/remove functions instead
        return self._case_map

    @property
    def resource_map(self) -> dict[str, ResourceFilter]:
        # Get only; use the set/remove functions instead
        return self._resource_map

    ## Sidecar Management ##
    def set_case_data(self, case_label: str, search_paths: list[Path]):
        """
        Set the search paths for a given case in the cohort

        :param case_label: The label for the case (and its search paths).
            If a case already exists with this label, replaces it; otherwise, a new case is created.
        :param search_paths: The paths that should be searched when finding files for this case.
        """
        # Get the list of paths for this case
        new_paths = self.find_row_files(search_paths)
        new_paths = np.array([str(k) if k is not None else "" for k in new_paths])

        # If this is a new case, create a new column to match
        if case_label not in self.case_map.keys():
            # Create a new row at the end of the dataset
            row_idx = self.rowCount()
            self.addRow(row_idx, new_paths)
            # Set the header to this new label
            self.setHeaderData(
                row_idx, qt.Qt.Vertical, case_label, qt.Qt.EditRole
            )
        # Otherwise, replace the row's values with the newly found paths
        else:
            # Find the column position which matches our resource label
            row_idx = np.argwhere(self.indices == case_label).flatten()[0]
            # Change the column's contents to our new list of paths
            self.setRow(row_idx, new_paths)

        # Save the new filter for later
        self.case_map[case_label] = search_paths

    def rename_case(self, old_name: str, new_name: str):
        # Check if a case map with this name already exists
        if old_name not in self.case_map.keys():
            raise ValueError(f"Cannot rename case '{old_name}'; it doesn't exist!")
        # Update the backing model
        row_idx = np.argwhere(self.indices == old_name).flatten()[0]
        self.setHeaderData(row_idx, qt.Qt.Vertical, new_name, qt.Qt.EditRole)
        # Update the case map to reflect the change
        case_map_entry = self.case_map.pop(old_name)
        self.case_map[new_name] = case_map_entry

    def drop_cases(self, names: list[str]):
        # Check the names before proceeding
        for name in names:
            # Check if a case map with this name exists
            if name not in self.case_map.keys():
                raise ValueError(f"Cannot delete case '{name}'; it doesn't exist!")

        # Do everything in one go to avoid partial corruption
        for name in names:
            # Update the backing model
            row_idx = np.argwhere(self.indices == name).flatten()[0]
            self.dropRow(row_idx)
            # Update the case map
            self.case_map.pop(name)

    def set_resource_data(self, resource_label: str, filter_entry: ResourceFilter):
        """
        Set the filters for a given resource in the cohort.

        :param resource_label: The label of the resource to update/create.
            If a filter already exists with this label, replaces it; otherwise, a new filter is created
        :param filter_entry: The filter entry to associate with the new/updated resource.
        """
        # Find and process the list of paths associated with this filter
        new_paths = self.find_column_files(filter_entry)
        new_paths = np.array([str(k) if k is not None else "" for k in new_paths])

        # If this is a new resource, create a new column to match
        if resource_label not in self.header:
            # Add a new column to the end of the dataset
            col_idx = self.columnCount()
            self.addColumn(col_idx, new_paths)
            # Set the header to this new label
            self.setHeaderData(
                col_idx, qt.Qt.Horizontal, resource_label, qt.Qt.EditRole
            )
        # Otherwise, replace the column's values with the newly found paths
        else:
            # Find the column position which matches our resource label
            col_idx = np.argwhere(self.header == resource_label).flatten()[0]
            # Change the model's contents to our new list of paths
            self.setColumn(col_idx, new_paths)

        # Save the filter for later
        self.resource_map[resource_label] = filter_entry

        # Mark ourselves as being changed
        self._mark_changed()

    def rename_resource(self, old_name: str, new_name: str, task_config: Optional[DictBackedConfig] = None):
        # Check that there's actually a filter to rename
        if old_name not in self.resource_map.keys():
            raise ValueError(f"Cannot rename resource '{old_name}'; it doesn't exist!")

        # Update the backing model
        col_idx = np.argwhere(self.header == old_name).flatten()[0]
        self.setHeaderData(col_idx, qt.Qt.Horizontal, new_name, qt.Qt.EditRole)

        # Update the resource entry to reflect the change
        resource_entry = self.resource_map.pop(old_name)
        self.resource_map[new_name] = resource_entry

        # If we have a reference task + config, have the task run renaming operations as well
        if self.reference_task and task_config:
            self.reference_task.rename_resource_config(old_name, new_name, task_config)

    def drop_resource(self, names: list[str]):
        # Check the names before proceeding
        for name in names:
            # Check if a case map with this name exists
            if name not in self.resource_map.keys():
                raise ValueError(f"Cannot delete resource '{name}'; it doesn't exist!")

        # Do everything in one go to avoid partial corruption
        for name in names:
            # Update the backing model
            col_idx = np.argwhere(self.header == name).flatten()[0]
            self.dropColumn(col_idx)
            # Update the case map
            self.resource_map.pop(name)

    ## Data Management ##
    @property
    def data_path(self) -> Optional[Path]:
        return self._data_path

    @data_path.setter
    def data_path(self, new_path: Path):
        if new_path is None or not new_path.is_dir():
            self._data_path = None
        else:
            self._data_path = new_path

    @property
    def csv_data(self) -> "Optional[npt.NDArray]":
        if self._csv_data is None:
            return None
        return self._csv_data[1:, 1:]

    @property
    def header(self) -> "npt.NDArray[str]":
        return self._csv_data[0, 1:]

    @property
    def indices(self) -> "npt.NDArray[str]":
        data = self._csv_data[1:, 0]
        return data

    def data(self, index: qt.QModelIndex, role=qt.Qt.DisplayRole):
        # If this is a tooltip role, add the corresponding tooltip
        if role == qt.Qt.ToolTipRole and self.is_editable():
            row_name = self.indices[index.row()]
            col_name = self.header[index.column()]
            return _(
                "Double-click to manually set the value of this cell.\n"
                "Right click to edit the settings for the entire case "
                f"({row_name}) or resource ({col_name});\n"
                "This will update ALL cells for that row/column!"
            )
        # Otherwise, delegate to the superclass
        return super().data(index, role)

    def headerData(self, section: int, orientation: qt.Qt.Orientation, role: int = ...):
        # Note; "section" -> column for Horizontal, row for Vertical
        if role == qt.Qt.DisplayRole:
            if orientation == qt.Qt.Horizontal:
                # Get the CSV value at this position
                csv_label = self.header[section]

                # Use the "pretty" name instead
                return self.csv_to_pretty(csv_label)
            elif orientation == qt.Qt.Vertical:
                return self.indices[section]
        return None

    def removeColumns(self, column, count, parent = ...):
        self.beginRemoveColumns(parent, column, column + count - 1)
        # Offset by 1 to account for the new UID column
        idx = [column + i + 1 for i in range(count)]
        self._csv_data = np.delete(self._csv_data, idx, axis=1)
        self.endRemoveColumns()

    def setHeaderData(self, section, orientation, value, role=...):
        if role == qt.Qt.EditRole:
            if orientation == qt.Qt.Horizontal:
                self.header[section] = value
            elif orientation == qt.Qt.Vertical:
                self.indices[section] = value
            self.headerDataChanged(orientation, section, section)

    ## File Searching/Filtering ##
    def find_first_valid_file(
        self, search_paths: list[Path], filters: ResourceFilter
    ) -> Optional[Path]:
        # If we don't have a data path to search within, return nothing
        if self.data_path is None:
            return None

        # If both filters are blank, assume the user wants nothing rather than an effectively random file.
        n_includes = len(filters.include)
        n_excludes = len(filters.exclude)
        if n_includes < 1 and n_excludes < 1:
            logging.info("No filters were given, assuming user wanted a blank entry.")
            return None

        # Search every path in turn
        result = None
        for p in search_paths:
            # If the path isn't absolute, root it to our data path
            if not p.is_absolute():
                p = self.data_path / p
            # Only look at files; directories (such as DICOM) are currently not supported for automated cohorts
            # TODO: Replace with path.walk when it becomes available
            for r, __, fs in os.walk(p, topdown=True):
                r = Path(r)
                for f in fs:
                    f = r / f
                    file_string = str(f)
                    # Check if all inclusion criterion were met
                    if n_includes != 0 and any([i not in file_string for i in filters.include]):
                        continue
                    # Check that all exclusion criterion were met
                    if n_excludes != 0 and any([i in file_string for i in filters.exclude]):
                        continue
                    # Check if our extension matches
                    if not file_string.endswith(filters.extension):
                        continue
                    # If all prior checks passed, track the file and end
                    result = f
                    break
                # Else-continue-break chain, allowing for the break to chain up the loops
                else:
                    continue
                break
            else:
                continue

        # If no valid files were found, return empty-handed
        if result is None:
            return None
        # If the result is within the data dir, make it relative
        elif self.data_path in result.parents:
            return result.relative_to(self.data_path)
        # Otherwise, return the result as-is
        else:
            return result

    def find_row_files(self, search_paths: list[Path]) -> list[Optional[Path]]:
        result_map = {}
        for k, v in self.resource_map.items():
            result_map[k] = self.find_first_valid_file(search_paths, v)
        sorted_pathlist = [result_map.get(k, None) for k in self.header]
        return sorted_pathlist

    def find_column_files(self, column_filters: ResourceFilter) -> list[Optional[Path]]:
        result_map = {}
        for k, v in self.case_map.items():
            result_map[k] = self.find_first_valid_file(v, column_filters)
        sorted_pathlist = [result_map.get(k, None) for k in self.indices]
        return sorted_pathlist

    ## I/O ##
    VERSION_KEY = "cohort_version"
    CASE_PATH_KEY = "case_paths"
    FILTERS_KEY = "filters"

    def save(self):
        # Only save if we have changed
        if self.has_changed:
            # Save the CSV (super-class delegate)
            super().save()
            # Save the sidecar as well, if requested
            if self.use_sidecar:
                self._save_sidecar()
            # Mark ourselves as unchanged
            self.has_changed = False

    def _save_sidecar(self):
        # Process the named tuples as dicts so the sidecars are human-readable
        filters = {
            k: v._asdict() for k, v in self.resource_map.items()
        }

        # Save the sidecar data on its own.
        sidecar_data = {
            self.VERSION_KEY: COHORT_VERSION,
            self.CASE_PATH_KEY: {
                k: [str(x) for x in v] for k, v in self.case_map.items()
            },
            self.FILTERS_KEY: filters,
        }

        with open(self.sidecar_path, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)

    def load(self):
        # Load the CSV contents
        super().load()
        # Load the sidecar contents as well if requested
        if self.use_sidecar:
            self._load_sidecar()
        # Mark ourselves as unchanged
        self.has_changed = False

    def _load_sidecar(self):
        # If this is for a not-yet-created cohort...
        if not self.csv_path:
            # ... reset everything and end
            self._case_map = dict()
            self._resource_map = dict()
            self._csv_data = None
            return
        # If we're just missing the sidecar...
        elif not self.sidecar_path.exists():
            # ... just reset the relevant contents instead
            self._case_map = dict()
            self._resource_map = dict()
            return
        # Otherwise, use the sidecar's contents to update ourselves
        with open(self.sidecar_path, "r") as fp:
            case_path_data = json.load(fp)

        # Update the case map
        case_data = case_path_data.get(self.CASE_PATH_KEY)
        if type(case_data) is not dict:
            raise ValueError(
                f"Cannot load sidecar, '{self.CASE_PATH_KEY}' was malformed!"
            )
        self._case_map = {k: [Path(x) for x in v] for k, v in case_data.items()}

        # Update the filters
        filter_data = case_path_data.get(self.FILTERS_KEY, {})
        if type(filter_data) is not dict:
            raise ValueError(
                f"Cannot load sidecar, '{self.FILTERS_KEY}' was malformed!"
            )
        # Parse each entry as a dictionary to restore order in case the user modified the sidecar themselves
        self._resource_map = {k: ResourceFilter(**v) for k, v in filter_data.items()}

    ## Utilities ##
    @contextmanager
    def temporarily_editable(self):
        if self.is_editable():
            yield
        else:
            self.set_editable(True)
            yield
            self.set_editable(False)

    def csv_to_original(self, csv_label: str) -> Optional[str]:
        # Return the "original" name (provided by the user) for this resource
        resource = self.resource_map.get(csv_label)
        if resource is None:
            return None
        return resource.original_name

    def csv_to_resource_type(self, csv_label: str) -> "Optional[ResourceType]":
        # If we don't have a reference task, there are no resource types (yet)
        if self.reference_task is None:
            return None

        # Get the resource associated with this label; return None if we couldn't find one
        resource = self.resource_map.get(csv_label)
        if resource is None:
            return None

        # Get the type of resource for this instance
        duf = self.reference_task.getDataUnitFactory()
        resource_type: "ResourceType" = duf.resource_types().get(resource.resource_type)

        return resource_type

    def csv_to_pretty(self, csv_label: str) -> Optional[str]:
        # Get the resource for this label
        resource = self.resource_map.get(csv_label)
        if resource is None:
            return None

        # Get the type of resource for this instance
        resource_type = self.csv_to_resource_type(csv_label)
        if resource_type is None:
            return csv_label

        # If the resource doesn't have an original name, use the CSV name instead
        original_label = self.csv_to_original(csv_label)
        # Use the CSV string as a fallback if there's no original label
        if original_label is None:
            return resource_type.format_for_gui(csv_label)
        else:
            return resource_type.format_for_gui(original_label)


## Generators ##
class CaseGenerator(Protocol):
    """
    Function-like Protocol class for generating an initial set of cases.

    Allows for type-hinting, aiding in the registration of custom case generators for future extensions.
    """

    def __call__(self, data_path: Path) -> CaseMap: ...


# Default generators; simple BIDS support + blank slate
def _bids_cases(data_path: Path) -> CaseMap:
    # Identify the initial "source" paths
    subject_map = {}
    session_map = {}
    # Search by subject first
    for p in data_path.glob("sub*/"):
        # Find any sessions associated with this subject
        ses_ps = list(p.glob("ses*/"))
        # If there were none, use the subject alone for this case
        if len(ses_ps) < 1:
            subject = p.parts[-1]
            subject_map[subject] = [p.relative_to(data_path)]
        # Otherwise, prepare a case for each session
        else:
            for p2 in ses_ps:
                subject = p2.parts[-2]
                session = p2.parts[-1]
                key = f"{subject}__{session}"
                session_map[key] = [p2.relative_to(data_path)]

    # Add associated derivative paths, if such a directory exists
    derivative_path = data_path / "derivatives"
    if not derivative_path.exists():
        logging.warning("No derivatives path found for BIDS directory, skipping.")
    else:
        # Parse subject-only cases
        for subject, val_list in subject_map.items():
            val_list.extend([
                p.relative_to(data_path)
                for p in derivative_path.glob(f"*/{subject}/")
            ])
        # Parse session-based cases
        for key, val_list in session_map.items():
            subject, session = key.split("__")
            val_list.extend([
                p.relative_to(data_path)
                for p in derivative_path.glob(f"*/{subject}/{session}/")
            ])
    # Stack everything together
    case_map = {k: v for k, v in subject_map.items()}
    case_map.update(session_map)
    # Sort the results to make them easier to work with
    case_map = {k: case_map[k] for k in sorted(case_map.keys())}
    return case_map


def _blank(__: Path) -> CaseMap:
    return dict()


# Registry for cases to be displayed during Cohort init
CASE_GENERATORS: dict[str, CaseGenerator] = {
    "BIDS": _bids_cases,
    "Blank Slate": _blank,
}

GENERATOR_DESCRIPTIONS: dict[str, str] = {
    "BIDS": _(
        "Iterate through your BIDS dataset on a per-subject and per-session basis. "
        "If multiple sessions are present, will iterate through them one-at-a-time. "
        "Looks for the 'sub' prefix to identify subjects, and 'ses' for sessions."),
    "Blank Slate": _(
        "Generate a completely emply cohort file. You will need to add each case "
        "manually; this only generates the (blank) files needed for a cohort file "
        "to be managed by CART."
    )
}

def register_case_generator(label: str, description: str, generator: CaseGenerator):
    if label in CASE_GENERATORS.keys():
        raise ValueError(
            f"Cannot register generator '{label}', an existing generator with that label already exists!"
        )
    GENERATOR_DESCRIPTIONS[label] = description
    CASE_GENERATORS[label] = generator


def cohort_from_generator(
    cohort_path: Path, data_path: Path, generator: CaseGenerator
) -> CohortModel:
    """
    Generate a cohort from scratch, using the provided generator and input dataset.

    :param cohort_path: The to-be-created (or overwritten) cohort file path
    :param data_path: The data path to reference when finding cases
    :param generator: The generator to user.
    """
    # Build the case map from the generator
    case_map = generator(data_path)
    # Create the cohort model from that
    cohort = CohortModel.from_case_map(
        csv_path=cohort_path, data_path=data_path, case_map=case_map
    )
    return cohort


## Related Widgets ##
class CohortTableView(qt.QTableView):
    """
    Provides a default context menu for use w/ this class of widgets.

    Generally, however, you should use CohortTableWidget (below) instead.
    """

    def __init__(
        self,
        task_config: DictBackedConfig = None,
        parent: qt.QObject = None
    ):
        """
        Constructor

        :param parent: The parent widget for QT hierarchy management.
        """
        super().__init__(parent)

        # Track the task config for later
        self.task_config = task_config

        # Change the layout to be more sensible
        self.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.verticalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.setHorizontalScrollMode(qt.QAbstractItemView.ScrollPerPixel)

        # Delegate context menu creation (right-click) to our own custom functions instead
        self.setContextMenuPolicy(qt.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._presentCellContextMenu)

        # Header/Index Specific Connections
        verticalHeader: qt.QHeaderView = self.verticalHeader()
        verticalHeader.sectionDoubleClicked.connect(self._caseLabelDoubleClicked)
        verticalHeader.setContextMenuPolicy(qt.Qt.CustomContextMenu)
        verticalHeader.customContextMenuRequested.connect(self._presentIndexContextMenu)

        horizontalHeader: qt.QHeaderView = self.horizontalHeader()
        horizontalHeader.sectionDoubleClicked.connect(self._resourceLabelDoubleClicked)
        horizontalHeader.setContextMenuPolicy(qt.Qt.CustomContextMenu)
        horizontalHeader.customContextMenuRequested.connect(self._presentHeaderContextMenu)

    @property
    def selectedItemsChanged(self):
        # Alias for the underlying selection model's "selection changed" object
        return self.selectionModel().selectionChanged

    ## Double-click Actions
    @qt.Slot(int)
    def _caseLabelDoubleClicked(self, idx: int):
        # If the table we're viewing isn't editable, do nothing
        m: "CohortModel" = self.model()
        if not m.is_editable():
            return
        # Prompt the user to edit the corresponding case
        row_id = m.indices[idx]
        self._caseEditorPrompt(row_id)

    @qt.Slot(int)
    def _resourceLabelDoubleClicked(self, idx: int):
        # If the table we're viewing isn't editable, do nothing
        m: "CohortModel" = self.model()
        if not m.is_editable():
            return
        # Prompt the user to edit the corresponding resource
        col_id = m.header[idx]
        self._resourceEditorPrompt(col_id)

    ## Context (Right-Click) Actions ##
    @qt.Slot(qt.QPoint)
    def _presentCellContextMenu(self, pos: qt.QPoint):
        """
        Create and display a context menu for the table's cell at the given position.
        """
        # If our managed cohort isn't editable, terminate early
        if not self.model().is_editable():
            return

        # If the corresponding index is invalid, end here
        idx = self.indexAt(pos)
        if not idx.isValid():
            return

        # Build the context menu
        menu = qt.QMenu(self)
        self._installRowActions(menu, idx)
        self._installColActions(menu, idx)

        # Show it to the user
        # noinspection PyArgumentList
        menu.popup(self.viewport().mapToGlobal(pos))

    def _presentIndexContextMenu(self, pos: qt.QPoint):
        """
        Create and display a context menu for the table index (row header) at the given position.
        """

        # If our managed cohort isn't editable, terminate early
        if not self.model().is_editable():
            return

        # If the corresponding index is invalid, end here
        idx: qt.QModelIndex = self.indexAt(pos)
        if not idx.isValid():
            return

        # Install row actions only
        menu = qt.QMenu(self)
        self._installRowActions(menu, idx)

        # Show it to the user
        # noinspection PyArgumentList
        menu.popup(self.verticalHeader().viewport().mapToGlobal(pos))

    def _presentHeaderContextMenu(self, pos:qt.QPoint):
        """
        Create and display a context menu for the table's (column) header at the given position.
        """

        # If our managed cohort isn't editable, terminate early
        if not self.model().is_editable():
            return

        # If the corresponding index is invalid, end here
        idx: qt.QModelIndex = self.indexAt(pos)
        if not idx.isValid():
            return

        # Install column actions only
        menu = qt.QMenu(self)
        self._installColActions(menu, idx)

        # Show it to the user
        # noinspection PyArgumentList
        menu.popup(self.horizontalHeader().viewport().mapToGlobal(pos))

    def _installRowActions(self, menu: qt.QMenu, idx: qt.QModelIndex):
        # Get the case to generate the object for
        row_id = self.model().indices[idx.row()]

        # Modification action
        editAction = menu.addAction(_(f"Modify {row_id}"))
        editAction.triggered.connect(lambda: self._caseEditorPrompt(row_id))

    def _installColActions(self, menu: qt.QMenu, idx: qt.QModelIndex):
        # Get the case label for ease-of-use
        model: CohortModel = self.model()
        col_id = model.header[idx.column()]
        col_pretty = model.csv_to_pretty(col_id)

        # Modification action
        editAction = menu.addAction(_(f"Modify {col_pretty}"))
        editAction.triggered.connect(lambda: self._resourceEditorPrompt(col_id))

    ## Other Utilities ##
    def editSelectedCase(self):
        # Get the list of currently selected cases
        selected_rows = {idx.row() for idx in self.selectionModel().selectedIndexes}
        row_ids = [self.model().indices[i] for i in selected_rows]

        # If the number of selected rows is one, just proceed to edit it
        if len(row_ids) < 2:
            self._caseEditorPrompt(row_ids[0])
            return

        # Otherwise, prompt the user to select one of the options first
        dialog = qt.QInputDialog(self)
        dialog.setWindowTitle(_("Multiple Cases Selected"))
        dialog.setLabelText(_("Please Select a Case: "))
        dialog.setComboBoxItems(row_ids)

        # Only proceed to the editor if the
        if dialog.exec() == qt.QDialog.Accepted:
            row_id = dialog.textValue()
            if row_id is not None:
                self._caseEditorPrompt(row_id)

    def _caseEditorPrompt(self, row_id):
        dialog = CaseEditorDialog(self.model(), row_id)
        if dialog.exec():
            # Without this, the cells rapidly bloat for some reason
            self.resizeColumnsToContents()
            self.resizeRowsToContents()

    def editSelectedResource(self):
        # Get the list of currently selected resources
        selected_columns = {idx.column() for idx in self.selectionModel().selectedIndexes}
        col_ids = [self.model().header[i] for i in selected_columns]

        # If the number of selected rows is one, just proceed to edit it
        if len(col_ids) < 2:
            self._resourceEditorPrompt(col_ids[0])
            return

        # Otherwise, prompt the user to select one of the options first
        dialog = qt.QInputDialog(self)
        dialog.setWindowTitle(_("Multiple Resources Selected"))
        dialog.setLabelText(_("Please Select a Resource: "))
        m: CohortModel = self.model()
        pretty_map = {m.csv_to_pretty(c): c for c in col_ids}
        dialog.setComboBoxItems(list(pretty_map.keys()))

        # Only proceed to the editor if the user selected one of the valid resources
        if dialog.exec() == qt.QDialog.Accepted:
            selected_col = dialog.textValue()
            col_id = pretty_map.get(selected_col)
            if col_id is not None:
                self._resourceEditorPrompt(col_id)

    def _resourceEditorPrompt(self, col_id):
        dialog = ResourceEditorDialogue(
            cohort=self.model(), resource_name=col_id, task_config=self.task_config
        )
        if dialog.exec():
            # Without this, the cells rapidly bloat for some reason
            self.resizeColumnsToContents()
            self.resizeRowsToContents()

    ## Dunders ##
    def __del__(self):
        # Disconnect change events; PythonQT isn't smart enough to clean up
        #  self-referential actions it seems.
        if self.model() is not None:
            self.model().disconnectChangeEvents()


class CohortTableWidget(CSVBackedTableWidget):
    """
    Modified version of the CSVBackedTableWidget which tracks a
    CohortTableView instead.
    """

    def __init__(
        self,
        model: CohortModel,
        task_config: Optional[DictBackedConfig] = None,
        parent: qt.QWidget = None,
    ):
        """
        Constructor

        :param model: The cohort model to view within this widget.
        :param parent: The parent widget for QT hierarchy management.
        """
        super().__init__(model, parent)

        # Swap to our (contex-menu providing) table view class.
        self.tableView = CohortTableView(task_config=task_config)
        self.tableView.setModel(model)
        self.refresh()

    @classmethod
    def from_path(
        cls,
        csv_path: Optional[Path] = None,
        data_path: Optional[Path] = None,
        editable: bool = True
    ):
        model = CohortModel(csv_path, data_path, editable=editable)
        return cls(model)

    @property
    def selectedItemsChanged(self) -> qt.Signal:
        # Alias for our managed table's "selectedItemsChanged" signal
        return self.tableView.selectedItemsChanged


## Related Dialogues ##
class NewCohortDialog(ChangeTrackingDialogue):
    def __init__(
        self,
        data_path: Path,
        output_path: Optional[Path] = None,
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # Track the data path for later
        self.data_path = data_path
        self.output_path = output_path

        # Initial setup
        self.setWindowTitle(_("New Cohort"))
        layout = qt.QFormLayout(self)

        # Make ourselves wider initially so the placeholder text is more clear
        self.resize(400, self.minimumHeight)

        # Name to give the cohort
        cohortNameLabel = qt.QLabel(_("Destination File: "))
        cohortFileEdit = CARTPathLineEdit()
        cohortNameTooltip = _(
            "A CSV file with cases generated based on your input file will be created "
            "when this prompt is closed; you can select (and edit) it later if you need to."
        )
        cohortNameLabel.setToolTip(cohortNameTooltip)
        cohortFileEdit.setToolTip(cohortNameTooltip)
        # Placeholder and default text
        cohortFileEdit.setCurrentPath("cohort.csv")
        cohortFileEdit.setPlaceholderText(_(
            "i.e. home/user/output.csv"
        ))
        # Allow the user to create files as well
        cohortFileEdit.filters = cohortFileEdit.filters | ctk.ctkPathLineEdit.Writable
        # Make sure only CSV files are visible (and valid)
        cohortFileEdit.nameFilters = [
            "CSV files (*.csv)",
        ]
        self._cohortFileEdit = cohortFileEdit
        layout.addRow(cohortNameLabel, cohortFileEdit)

        # Type of cohort to generate
        cohortTypeComboBox = qt.QComboBox(None)
        cohortTypeLabel = qt.QLabel(_("Cohort Type: "))
        cohortTypeComboBox.addItems(list(CASE_GENERATORS.keys()))
        self._cohortTypeComboBox = cohortTypeComboBox
        layout.addRow(cohortTypeLabel, cohortTypeComboBox)

        # Description of said type
        cohortTypeDescription = qt.QTextBrowser(None)
        cohortTypeDescription.setText(
            _("Details about the selected cohort type will appear here.")
        )
        # Fill all available space
        cohortTypeDescription.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )
        # Add a border around it to visually distinguish it
        cohortTypeDescription.setFrameShape(qt.QFrame.Panel)
        cohortTypeDescription.setFrameShadow(qt.QFrame.Sunken)
        cohortTypeDescription.setLineWidth(3)
        # Align text to the upper-left
        cohortTypeDescription.setAlignment(qt.Qt.AlignLeft | qt.Qt.AlignTop)
        # Make it read-only
        cohortTypeDescription.setReadOnly(True)
        layout.addRow(cohortTypeDescription)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )
        layout.addWidget(buttonBox)
        # Disable the OK button until the user selects valid options
        self._ok_button = buttonBox.button(qt.QDialogButtonBox.Ok)

        # Connections
        @qt.Slot(str)
        def onCohortChanged(__: str):
            # Disable the button if the file changed
            self.validate()
            self.mark_changed()

        cohortFileEdit.textChanged.connect(onCohortChanged)

        @qt.Slot(str)
        def onCohortTypeChanged(new_txt: str):
            # Update the preview text to match the new selection
            new_description = GENERATOR_DESCRIPTIONS.get(new_txt, _("Missing description for this case generator!"))
            cohortTypeDescription.setText(new_description)
            self.validate()
            self.mark_changed()

        cohortTypeComboBox.currentTextChanged.connect(onCohortTypeChanged)

        @qt.Slot(qt.QPushButton)
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)

        # Run validation to sync everything up
        self.validate()

    @property
    def cohort_file(self) -> Optional[Path]:
        # Workaround to CTK not playing nicely w/ "registerField"
        path = self._cohortFileEdit.currentPath
        if path == '':
            return None
        # Conver the path into an absolute path, if need be
        path = Path(path)
        if path.is_absolute():
            return path
        elif self.output_path is None:
            return None
        else:
            return self.output_path / path

    @property
    def current_generator(self) -> Optional[CaseGenerator]:
        # noinspection PyTypeChecker
        return CASE_GENERATORS.get(self._cohortTypeComboBox.currentText, None)

    def validate(self):
        # Enable/disable the button based on current values
        self._ok_button.setEnabled(
            self.cohort_file is not None and self.current_generator
        )


class CohortEditorDialog(ChangeTrackingDialogue):
    """
    GUI Dialog for editing a given cohort file.

    Using the button panel, users can add, edit, or delete rows/columns within the cohort.

    The user can manually add, remove, edit the rows/columns within the table widget itself.
    """

    def __init__(
        self,
        cohort: CohortModel,
        task_config: DictBackedConfig,
        parent: qt.QObject = None,
    ):
        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        super().__init__(parent)

        # QT is astonishingly shit at handling itself, so we need to track
        #  connections to disconnect later
        self._to_disconnect = []

        # Backing cohort manager
        self._cohort: qt.QAbstractTableModel = cohort

        # Track a parent-less copy of the config
        # (parent-less to prevent changes propagating upwards prematurely)
        self._original_task_config = task_config
        self._task_config = copy.deepcopy(task_config)
        self._task_config.parent_config = None

        # Initial setup
        self.setWindowTitle(_("Cohort Editor"))
        layout = qt.QVBoxLayout(self)

        # Initially expand ourselves to make the contents clearer
        self.resize(900, 700)

        # Main table widget
        cohortWidget = CohortTableWidget(self._cohort, self._task_config)
        cohortWidget.setFrameShape(qt.QFrame.Panel)
        cohortWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortWidget.setLineWidth(3)
        layout.addWidget(cohortWidget)
        self.cohortWidget = cohortWidget

        # Cohort Management Buttons
        self._addButtons(layout)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        @qt.Slot(qt.QPushButton)
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Only save changes to the cohort when confirmed!
                self._cohort.save()
                # Update our original config w/ any changes made to our modified config
                self._original_task_config.backing_dict = self._task_config.backing_dict
                self._original_task_config.has_changed = True
                # Accept and close
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        self._to_disconnect.append(buttonBox.clicked)
        layout.addWidget(buttonBox)

    def _addButtons(self, layout: "qt.QVBoxLayout"):
        ## Resource (Column) Specific ##
        resourceContainer = ctk.ctkCollapsibleGroupBox()
        resourceContainer.setTitle(_("Resource (Column) Operations"))
        resourceLayout = qt.QHBoxLayout(resourceContainer)
        layout.addWidget(resourceContainer)

        # New
        newResourceButton = qt.QPushButton(_("New"))
        newResourceButton.setToolTip(
            _(
                "Add a new resource to the cohort. All cases (rows) "
                "will be automatically populated wherever possible."
            )
        )

        newResourceButton.clicked.connect(self._addNewResource)
        self._to_disconnect.append(newResourceButton.clicked)
        resourceLayout.addWidget(newResourceButton)

        # Edit
        editResourceButton = qt.QPushButton(_("Edit"))

        editResourceButton.clicked.connect(
            lambda: self.cohortWidget.tableView.editSelectedResource()
        )
        self._to_disconnect.append(editResourceButton.clicked)
        # We never have elements selected initially
        editResourceButton.setEnabled(False)
        resourceLayout.addWidget(editResourceButton)

        # Drop
        dropResourcesButton = qt.QPushButton(_("Delete"))
        dropResourcesButton.setToolTip(
            _("Remove the selected resource(s) from the cohort. "
              "THIS CANNOT BE UNDONE!")
        )

        dropResourcesButton.clicked.connect(self._dropSelectedResources)
        self._to_disconnect.append(dropResourcesButton.clicked)
        # We never have elements selected initially
        dropResourcesButton.setEnabled(False)
        resourceLayout.addWidget(dropResourcesButton)

        ## Case (Row) Specific ##
        caseContainer = ctk.ctkCollapsibleGroupBox()
        caseContainer.setTitle(_("Case (Row) Operations"))
        caseLayout = qt.QHBoxLayout(caseContainer)
        layout.addWidget(caseContainer)

        # Add
        newCaseButton = qt.QPushButton(_("New"))
        newCaseButton.setToolTip(
            _(
                "Add a new case to the cohort. All resources (columns) "
                "will be automatically populated with corresponding files "
                "wherever possible."
            )
        )
        newCaseButton.clicked.connect(self._addNewCase)
        self._to_disconnect.append(newCaseButton.clicked)
        caseLayout.addWidget(newCaseButton)

        # Edit
        editCaseButton = qt.QPushButton(_("Edit"))

        editCaseButton.clicked.connect(
            lambda: self.cohortWidget.tableView.editSelectedCase()
        )
        self._to_disconnect.append(editCaseButton.clicked)
        # We never have elements selected initially
        editCaseButton.setEnabled(False)
        caseLayout.addWidget(editCaseButton)

        # Drop
        dropCasesButton = qt.QPushButton(_("Delete"))
        dropCasesButton.setToolTip(
            _(
                "Remove the selected case(s) from the cohort. "
                "THIS CANNOT BE UNDONE!"
            )
        )

        dropCasesButton.clicked.connect(self._dropSelectedCases)
        self._to_disconnect.append(dropCasesButton.clicked)
        # We never have elements selected initially
        dropCasesButton.setEnabled(False)
        caseLayout.addWidget(dropCasesButton)

        ## Global Connections ##
        @qt.Slot(qt.QItemSelection, qt.QItemSelection)
        def updateButtonsEnabled(selected: qt.QItemSelection, __: qt.QItemSelection):
            should_enable = len(selected.indexes()) > 0
            editResourceButton.setEnabled(should_enable)
            editCaseButton.setEnabled(should_enable)
            dropResourcesButton.setEnabled(should_enable)
            dropCasesButton.setEnabled(should_enable)

        self.cohortWidget.selectedItemsChanged.connect(updateButtonsEnabled)

    @property
    def has_changed(self):
        return super().has_changed or self._cohort.has_changed

    def _disconnectAll(self):
        # Why does the SmartClosingDialogue functionality cause
        # a memory leak w/ its default approach in this context?
        # Who the fuck knows!
        for v in self._to_disconnect:
            v.disconnect()

    def forceResize(self):
        # Without this, the cells rapidly bloat after edits for some reason
        self.cohortWidget.tableView.resizeColumnsToContents()
        self.cohortWidget.tableView.resizeRowsToContents()

    ## Slots ##
    @qt.Slot()
    def _addNewResource(self):
        dialog = ResourceEditorDialogue(
            cohort=self._cohort, task_config=self._task_config
        )
        if dialog.exec():
            self.forceResize()

    @qt.Slot()
    def _dropSelectedResources(self):
        # Prompt the user to confirm this is what they want to do
        msg = qt.QMessageBox()
        msg.setWindowTitle("Are you sure?")
        resource_names = {
            self._cohort.header[idx.column()]
            for idx in self.cohortWidget.selectedIndices
        }
        resource_points = "\n".join(["  * " + c for c in resource_names])
        msg.setText(
            "You are about to delete the following resources:\n"
            f"{resource_points}\n"
            f"Are you sure?"
        )
        msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
        # Only apply the deletion if confirmed by the user
        if msg.exec() == qt.QMessageBox.Yes:
            self._cohort.drop_filters(resource_names)

    @qt.Slot()
    def _addNewCase(self):
        dialog = CaseEditorDialog(self._cohort)
        if dialog.exec():
            self.forceResize()

    @qt.Slot()
    def _dropSelectedCases(self):
        # Prompt the user to confirm this is what they want to do
        msg = qt.QMessageBox()
        msg.setWindowTitle("Are you sure?")
        case_names = {
            self._cohort.indices[idx.row()]
            for idx in self.cohortWidget.selectedIndices
        }
        case_points = "\n".join(["  * " + c for c in case_names])
        msg.setText(
            "You are about to delete the following cases:\n"
            f"{case_points}\n"
            f"Are you sure?"
        )
        msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
        # Only apply the deletion if confirmed by the user
        if msg.exec() == qt.QMessageBox.Yes:
            self._cohort.drop_cases(case_names)


class ResourceEditorDialogue(ChangeTrackingDialogue):

    def __init__(
        self,
        cohort: CohortModel,
        resource_name: str = None,
        task_config: "Optional[DictBackedConfig]" = None,
        parent: qt.QObject = None,
    ):
        """
        Dialog for editing (or creating) new resources within a cohort.

        :param cohort: The Cohort to apply the edits to
        :param resource_name: The name of the resource (within the cohort CSV) to edit.
            If None, will create a resource with the user specified name instead.
        :param task_config: A (parent-less!) task config that the resource this dialog
            is managing should reference and modify.
        :param parent: Parent widget, as required by QT.
        """
        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        # Initial setup
        super().__init__(parent)
        self.setSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Minimum)

        # Backing cohort model
        self._cohort = cohort

        # Track whether our own entries have changed or not
        self._has_changed = False

        # Track the previous resource's details (if any)
        self._prior_resource_name = resource_name
        self._active_resource_name = resource_name
        self._prior_resource = cohort.resource_map.get(resource_name)

        # Track the task config for later
        self.task_config = task_config
        self.task_config_copy = copy.deepcopy(task_config)

        # Cached map of the resource types for this provided task
        duf = cohort.reference_task.getDataUnitFactory()
        self._resource_type_map = {v.pretty_name: v for v in duf.resource_types().values()}

        # Initial setup
        if resource_name:
            pretty_name = cohort.csv_to_pretty(resource_name)
            self.setWindowTitle(_(f"Editing Resource '{pretty_name}'"))
        else:
            self.setWindowTitle(_("Add New Resource"))

        # Initially widen to show more of the contents
        self.resize(500, self.minimumHeight)
        layout = qt.QFormLayout(self)

        # Warning to notify the user; managed by the resource-type GUI (below)
        self.warningLabel = qt.QLabel()

        ## Field Selection GUI ##
        self._generateResourceTypeGUI(layout)

        ## Field Name GUI ##
        nameLabel = qt.QLabel(_("Resource Name:"))
        nameField = qt.QLineEdit()
        if resource_name:
            nameField.setText(cohort.csv_to_original(resource_name))
        nameField.setPlaceholderText(_("e.g. disk_labels, spinal_T2w, liver_segmentation"))
        nameTooltip = _(
            "The name you'd like this resource to have. "
            "This can be anything you'd like; just don't use any commas."
        )
        nameLabel.setToolTip(nameTooltip)
        nameField.setToolTip(nameTooltip)
        layout.addRow(nameLabel, nameField)
        nameField.textChanged.connect(self.mark_changed)
        self.nameField = nameField

        # Place the warning label (if any) here.
        layout.addRow(self.warningLabel)

        ## Include/Exclude/Extension Fields ##
        includeLabel = qt.QLabel(_("Include:"))
        includeField = qt.QLineEdit()
        if resource_name:
            resource = self._cohort.resource_map.get(resource_name)
            include_vals = resource.include
            if include_vals is None:
                includeField.setText("")
            else:
                includeField.setText(", ".join(include_vals))
        includeTooltip = _(
            "Comma-separated elements that a file MUST have to be used for this resource. "
            "This incudes the directory the file is contained within!"
        )
        includeLabel.setToolTip(includeTooltip)
        includeField.setToolTip(includeTooltip)
        includeField.setPlaceholderText(_("e.g. 'T1w, lesion_seg, axial'"))
        self.includeField = includeField
        layout.addRow(includeLabel, includeField)

        excludeLabel = qt.QLabel(_("Exclude:"))
        excludeField = qt.QLineEdit()
        if resource_name:
            resource = self._cohort.resource_map.get(resource_name, None)
            if resource is None or resource.exclude is None:
                excludeField.setText("")
            else:
                excludeField.setText(", ".join(resource.exclude))
        excludeTooltip = _(
            "Comma-separated elements that a file MUST NOT have to be used for this resource. "
            "This incudes the directory the file is contained within!"
        )
        excludeLabel.setToolTip(excludeTooltip)
        excludeField.setToolTip(excludeTooltip)
        excludeField.setPlaceholderText(_("e.g. 'derivatives, masked, brain'"))
        self.excludeField = excludeField
        layout.addRow(excludeLabel, excludeField)

        extensionLabel = qt.QLabel(_("Extension:"))
        extensionField = qt.QLineEdit()
        if resource_name:
            resource = self._cohort.resource_map.get(resource_name, None)
            if resource is None or resource.exclude is None:
                extensionField.setText("")
            else:
                extensionField.setText(resource.extension)
        extensionTooltip = _(
            "The file extension to filter for. Leave blank to accept any file type."
        )
        extensionLabel.setToolTip(extensionTooltip)
        extensionField.setToolTip(extensionTooltip)
        extensionField.setPlaceholderText(_("e.g. .nii.gz"))
        defaultExtension = ".nii.gz" # Default to NIfTI format
        if resource_name:
            resource = self._cohort.resource_map.get(resource_name)
            prior_extension = resource.extension
            if prior_extension is None:
                extensionField.setText(defaultExtension)
            else:
                extensionField.setText(prior_extension)
        else:
            extensionField.setText(defaultExtension)
        self.extensionField = extensionField
        layout.addRow(extensionLabel, extensionField)

        # Mark the cohort as being changed if any of the fields change
        includeField.textChanged.connect(self.mark_changed)
        excludeField.textChanged.connect(self.mark_changed)
        extensionField.textChanged.connect(self.mark_changed)

        # Container widget to hold the resource-specific task GUI
        self.taskConfigBox: qt.QWidget = qt.QWidget(self)
        self._initTaskConfigGUI()
        self.resourceTypeSelector.currentIndexChanged.connect(self._rebuildTaskConfigGUI)
        layout.addRow(self.taskConfigBox)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        @qt.Slot(qt.QPushButton)
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Attempt to apply the requested changes before closing
                if self.apply_changes():
                    self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")
        buttonBox.clicked.connect(onButtonClicked)

        # Add it to the layout w/ a stretch to force them to the bottom
        stretch = qt.QWidget(self)
        stretch.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        layout.addWidget(stretch)
        layout.addWidget(buttonBox)

        # Minimize ourselves to the minimum size vertically initially
        self.resize(self.width, self.minimumHeight)

    def _generateResourceTypeGUI(self, layout: "qt.QFormLayout"):
        # Resource type selector and description
        resourceTypeLabel = qt.QLabel(_("Resource Type:"))
        resourceTypeSelector = qt.QComboBox(None)
        resourceTypeSelector.addItems(list(self._resource_type_map.keys()))
        resourceTypeToolTip = _(
            "The resource type for this column."
            "\n\n"
            "Most tasks will use the name of each resource to determine "
            "how to process the corresponding resource for each case; "
            "selecting the correct resource type ensures the task can "
            "do so successfully."
        )
        resourceTypeLabel.setToolTip(resourceTypeToolTip)
        resourceTypeSelector.setToolTip(resourceTypeToolTip)
        layout.addRow(resourceTypeLabel, resourceTypeSelector)

        # Default the resource type selector to select no type
        resourceTypeSelector.setCurrentIndex(-1)

        # Add it to the overall layout
        layout.addRow(resourceTypeLabel, resourceTypeSelector)

        ## Type Description Widget ##
        resourceTypeDescriptionBox: qt.QWidget = ctk.ctkCollapsibleGroupBox()
        resourceTypeDescriptionBox.setTitle(_("Type Description"))
        resourceTypeDescriptionBoxLayout = qt.QVBoxLayout()
        resourceTypeDescriptionBox.setLayout(resourceTypeDescriptionBoxLayout)
        # Allow the container to be if desired by the user
        resourceTypeDescriptionBox.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Preferred
        )

        # The description-handling widget itself
        default_description = _(
            "A description of the selected resource type will appear here"
        )
        resourceTypeDescription = qt.QTextBrowser(self)
        resourceTypeDescription.setOpenExternalLinks(True)
        # Align text to the upper-left
        resourceTypeDescription.setAlignment(qt.Qt.AlignLeft | qt.Qt.AlignTop)
        # Make it read-only
        resourceTypeDescription.setReadOnly(True)
        # Make it expand to be as large as it needs to be vertically, but not more
        resourceTypeDescription.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Preferred
        )
        # Add it to our layout
        resourceTypeDescriptionBoxLayout.addWidget(resourceTypeDescription)

        @qt.Slot(str)
        def onResourceTypeChanged(__: str):
            # Get the current resource type
            new_type = self.resource_type
            if new_type is None:
                # Update our description text to become our default widget
                resourceTypeDescription.setMarkdown(default_description)
                # Hide the warning label
                self.warningLabel.setVisible(False)
            else:
                # Update our description text to match
                resourceTypeDescription.setMarkdown(new_type.description)
                # Update the warning label to match
                should_show = new_type.user_warning is not None
                if should_show:
                    self.warningLabel.setText(new_type.user_warning)
                self.warningLabel.setVisible(should_show)
            # Mark ourselves as changed
            self.mark_changed()
            # Resize ourselves to account for any GUI changes if possible
            self.resize(self.width, self.minimumHeight)

        resourceTypeSelector.currentIndexChanged.connect(onResourceTypeChanged)

        # Track the resource selector for later
        self.resourceTypeSelector = resourceTypeSelector

        # Disable resource-type widgets for tasks which do not specify resource types
        if len(self._resource_type_map) < 2:
            resourceTypeSelector.setEnabled(False)
            resourceTypeDescriptionBox.setEnabled(False)
            disabledToolTip = _("The selected task did specify multiple resource types.")
            resourceTypeSelector.setToolTip(disabledToolTip)
            resourceTypeDescriptionBox.setToolTip(disabledToolTip)

        # Add it to the layout
        layout.addRow(resourceTypeDescriptionBox)

        # Match the selected resource type to the previous resource type (if possible)
        if self._prior_resource is not None:
            prior_type_id = self._prior_resource.resource_type
            if prior_type_id is not None:
                duf = self._cohort.reference_task.getDataUnitFactory()
                prior_type = duf.resource_types().get(prior_type_id)
                if prior_type is not None:
                    resourceTypeSelector.setCurrentText(prior_type.pretty_name)
                    # Reset our change state to prevent an erroneous "Unsaved Changes" pop-up
                    self._has_changed = False

    ## Resource-Specific Config Handling ##
    DUMMY_RESOURCE_NAME = "__dummy"

    def _initTaskConfigGUI(self):
        # If we don't have a valid resource type, hide the config GUI
        if self.resource_type is None:
            self.taskConfigBox.setVisible(False)
            return

        # If the resource lacks a valid GUI, also hide the config and end
        config_layout = self.resource_type.buildConfigGUI(self.task_config_copy, self._active_resource_name)
        if config_layout is None:
            self.taskConfigBox.setVisible(False)
            return

        # Make the configuration box visible
        self.taskConfigBox.setVisible(True)

        # Use the config layout as our new GUI
        self.taskConfigBox.setLayout(config_layout)

    @qt.Slot()
    def _rebuildTaskConfigGUI(self):
        # If the currently selected resource type is invalid, just hide the GUI
        if self.resource_type is None:
            self.taskConfigBox.setVisible(False)
            return

        # Have the task delete the previous resource's configuration settings
        self._cohort.reference_task.drop_resource_config(
            self._active_resource_name, self.task_config_copy
        )

        # Try to initialize a new config GUI for the current resource type under a "dummy" name
        config_layout = self.resource_type.buildConfigGUI(
            self.task_config_copy, self.DUMMY_RESOURCE_NAME
        )

        # Update the "active" label to match
        self._active_resource_name = self.DUMMY_RESOURCE_NAME

        # If there isn't one, just hide the GUI
        if config_layout is None:
            self.taskConfigBox.setVisible(False)
        # Otherwise, replace the GUI layout and show the result
        else:
            if self.taskConfigBox.layout() is not None:
                tmp = qt.QWidget(None)
                tmp.setLayout(self.taskConfigBox.layout())
                del tmp
            self.taskConfigBox.setLayout(config_layout)
            self.taskConfigBox.setVisible(True)

    def apply_changes(self):
        # Only run the (relatively) expensive update if something has changed
        # TODO: Move the following checks to be run dynamically, disabling the "OK" button
        #  until they are resolved.
        if not self.has_changed:
            return True

        # Confirm the user has selected a valid resource type
        if self.resource_type is None:
            # If not, show an error and return "False" (no changes made)
            qt.QMessageBox.critical(
                None,
                _("Invalid resource type"),
                _("You have either not selected a resource type, or the selected resource type is invalid. "
                  "Please select a (new) resource type before continuing."),
                qt.QMessageBox.Ok,
            )
            return False

        # Make sure the user has actually given a proper name
        base_str = self.nameField.text.strip()
        if base_str == "":
            # If not, show an error and return "False" (no changes made)
            qt.QMessageBox.critical(
                None,
                _("No Name Given"),
                _("You did not give this resource a name; please do so before proceeding."),
                qt.QMessageBox.Ok,
            )
            return False

        # Make sure a resource of this name doesn't already exist
        csv_str = self.resource_type.format_for_csv(base_str)
        pretty_str = self.resource_type.format_for_gui(base_str)
        if self._has_name_changed and csv_str in self._cohort.resource_map.keys():
            # If it does, show an error and return "False" (no changes made)
            qt.QMessageBox.critical(
                None,
                "Invalid Resource Name",
                f"'Resource of name {pretty_str}' ({csv_str}) already exists; "
                f"please change this resource's name or type to make it unique.",
                qt.QMessageBox.Ok,
            )
            return False

        # Update the cohort's contents
        self._apply_cohort_changes(base_str, csv_str)

        # Update the task config as well
        self._apply_config_changes(csv_str)

        # Signal that everything ran successfully
        return True

    def _apply_cohort_changes(self, base_str: str, csv_str: str):
        # Parse the contents of our GUI elements, stripping leading/trailing whitespace
        include_entries = [s.strip() for s in self.includeField.text.split(",") if s.strip() != ""]
        exclude_entries = [s.strip() for s in self.excludeField.text.split(",") if s.strip() != ""]
        extension_string = self.extensionField.text.strip()

        # Pack it into our named tuple
        filter_entry = ResourceFilter(
            original_name=base_str,
            resource_type=self.resource_type.id,
            include=include_entries,
            exclude=exclude_entries,
            extension=extension_string
        )

        print("-" * 100)
        print(filter_entry)

        # If this an updated resource, rename the resource to this new name
        if self._prior_resource is not None:
            self._cohort.rename_resource(self._prior_resource_name, csv_str)

        # Update cohort to use the new resource filter
        self._cohort.set_resource_data(csv_str, filter_entry)

    def _apply_config_changes(self, csv_str: str):
        # Have the task move active configuration settings to the current resource's name
        self._cohort.reference_task.rename_resource_config(
            self._active_resource_name, csv_str, self.task_config_copy
        )

        # Transfer any changes made to the task config copy to the "real" config
        self.task_config.backing_dict = self.task_config_copy.backing_dict

    ## Properties ##
    @property
    def _has_name_changed(self):
        # If we don't have a resource type yet, assume this is False.
        if self.resource_type is None:
            return False
        # Otherwise, check whether the name has been changed
        base_str = self.nameField.text.strip()
        csv_str = self.resource_type.format_for_csv(base_str)
        return csv_str != self._prior_resource_name

    @property
    def has_changed(self):
        # Check against our backing task config + name as well
        return any([self._has_changed, self.task_config_copy.has_changed, self._has_name_changed])

    @property
    def resource_type(self) -> "Optional[ResourceType]":
        current_text = self.resourceTypeSelector.currentText.strip()
        resource_type = self._resource_type_map.get(current_text)
        return resource_type

    @resource_type.setter
    def resource_type(self, new_type: "ResourceType"):
        # Make sure the provided resource type is one recognized by our mapping
        if new_type not in self._resource_type_map.values():
            raise ValueError(
                f"Resource type {new_type.pretty_name} is not a valid type for the selected data unit."
            )
        # Update our GUI (and everything else that follows) to match
        self.resourceTypeSelector.setCurrentText(new_type.pretty_name)


class CaseEditorDialog(ChangeTrackingDialogue):
    def __init__(self, cohort: CohortModel, case_id: str = None, parent: qt.QObject = None):
        """
        Dialog for editing (or creating) new resources within a cohort.

        :param cohort: The Cohort to apply the edits to
        :param case_id: The name of the case to edit. If None, will create a resource with
            the user specified name instead.
        :param parent: Parent widget, as required by QT.
        """
        super().__init__(parent)

        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        # Backing cohort manager
        self._cohort = cohort

        # Reference resource name
        self._reference_case = case_id

        # Nested signals which need to be disconnected to avoid a memory leak
        self._nested_connections = []

        # Initial setup
        if case_id:
            self.setWindowTitle(_(f"Editing Case '{case_id}'"))
        else:
            self.setWindowTitle(_("Add New Case"))
        layout = qt.QFormLayout(self)

        # Initially widen to show more of the contents
        self.resize(500, self.minimumHeight)

        # Name Field
        nameLabel = qt.QLabel(_("Case Name:"))
        nameField = qt.QLineEdit()
        if case_id:
            nameField.setText(case_id)
        nameField.setPlaceholderText(_("e.g. sub-001, sub001_ses002"))
        nameField.textChanged.connect(self.mark_changed)
        nameTooltip = _(
            "An identifier for this case. Should be unique to the cohort; ideally, it should also "
            "implicitly reference the data it will refer to as well "
            "(i.e. sub-001 refers to data in sub-001 associated directories)."
        )
        nameLabel.setToolTip(nameTooltip)
        nameField.setToolTip(nameTooltip)
        self.nameField = nameField
        layout.addRow(nameLabel, nameField)

        # Search path list
        searchPathLabels = qt.QLabel(_("Search Paths: "))
        searchPathList = qt.QListWidget(None)
        if case_id:
            path_entries = cohort.case_map.get(case_id, [])
            for p in path_entries:
                if p.is_absolute():
                    searchPathList.addItem(str(p))
                else:
                    searchPathList.addItem(str(cohort.data_path / p))

        model = searchPathList.model()
        model.rowsInserted.connect(self.mark_changed)
        model.rowsRemoved.connect(self.mark_changed)
        layout.addRow(searchPathLabels)
        layout.addRow(searchPathList)
        self.searchPathList = searchPathList
        self._nested_connections.append(model.rowsInserted)
        self._nested_connections.append(model.rowsRemoved)

        # Button panel
        addButton = qt.QPushButton("Add")
        removeButton = qt.QPushButton("Remove")
        removeButton.setEnabled(False)

        def onAddClicked():
            fileDialog = qt.QFileDialog(None)
            fileDialog.setDirectory(str(cohort.data_path))
            fileDialog.setFileMode(qt.QFileDialog.Directory)
            if fileDialog.exec():
                d = fileDialog.selectedFiles()[0]
                d = qt.QListWidgetItem(d)
                searchPathList.addItem(d)

        addButton.clicked.connect(onAddClicked)

        def onItemSelectionChanged():
            removeButton.setEnabled(len(searchPathList.selectedIndexes()) > 0)

        searchPathList.itemSelectionChanged.connect(onItemSelectionChanged)

        def onRemoveClicked():
            for i in searchPathList.selectedItems():
                searchPathList.takeItem(searchPathList.row(i))

        removeButton.clicked.connect(onRemoveClicked)

        # Make them side-by-side and add them to the layout
        w = qt.QWidget(None)
        l = qt.QHBoxLayout(w)
        l.addWidget(addButton)
        l.addWidget(removeButton)
        layout.addRow(w)

        self._nested_connections.append(addButton.clicked)
        self._nested_connections.append(removeButton.clicked)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Apply the requested changes to the cohort before closing.
                if self.apply_changes():
                    self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)

    def apply_changes(self):
        # Only run the (relatively) expensive update if something has changed
        if not self.has_changed:
            return True

        # Make sure a case with this name doesn't already exist
        label = self.nameField.text.strip()
        if self._reference_case is None and label in self._cohort.case_map.keys():
            # If it does, show an error and return "False" (no changes made)
            qt.QMessageBox.critical(
                None,
                "Invalid Case Name",
                f"A case with the name '{label}' already exists; please change it to be unique.",
                qt.QMessageBox.Ok,
            )
            return False

        # Parse the contents of our GUI elements, stripping leading/trailing whitespace
        search_paths: list[Path] = []
        for i in range(self.searchPathList.count):
            p = Path(self.searchPathList.item(i).text())
            if self._cohort.data_path in p.parents:
                search_paths.append(p.relative_to(self._cohort.data_path))
            else:
                search_paths.append(p)

        # If this is an updated case, rename it to match
        if self._reference_case:
            self._cohort.rename_case(self._reference_case, label)

        # Insert it into our cohort
        self._cohort.set_case_data(label, search_paths)

        # Confirm that the changes went through
        return True

    def _disconnectAll(self):
        super()._disconnectAll()
        for c in self._nested_connections:
            c.disconnect()
