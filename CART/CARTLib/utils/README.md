# Standardized CART Utilities

This package contains a number of utilities or structures which have a common enough use case (or have an unintuitive/difficult implementation) to be standardized across most CART applications. This readme provides an overview of the notable utilities provided, with a brief description of each.

## Table of Contents

* [BIDS Management](#bids-management)
* [Configuration Management](#configuration-management)
* [Data Handling](#data-handling)
  * [The CART Standard Format](#the-cart-standard-format) 
  * [Manual I/O Handling](#manual-io-handling)
* [Task Registration](#task-registration)
* [Widgets](#widgets)

## BIDS Management

Placed within `bids.py`, provides utilities for handling data organized in the BIDS format. Notable functions include:

### `check_pseudo_bids` 

Validates that the passed directory is organized in a BIDS-like manner. Checks for the presence of at least one `sub-` directory, and a `derivatives` directory.
### `generate_blank_cohort`

Generate a cohort file template, with one case row per `sub-` directory within the provided path.

### `fetch_bids_subject_map`

Generates a map of case (subject) IDs to the files within the BIDS directory that should be associated with them.

## Configuration Management

Placed within `config.py`, this provides a number of standard structures for managing, saving, and loading configuration options in CART. Notable elements include:

### `DictBackedConfig`

As the name suggests, this is a configuration handled back by a Python dictionary. For it to work in the context of CART's profiles, it has two attributes of note:

* `parent`: Another `DictBackedConfig` that this config should be stored within. 
  * In most cases, this will be the currently active profile's configuration passed during task initialization, making this a "child" of that profile.
  * If you do not provide one, you need to override `save_without_parent` to define how this configuration should be saved!
* `config_label`: A label that the parent config will use to track this config within itself. Can be overridden by passing a different label during construction (see `ProfileConfig` in [`config.py`](config.py) for an example of when that may be warranted.)

By using this class as a configuration manager for your task, you get the following for free:

* Allows you to mark when its contents has changed, which hooks into the GUI component (see [`ConfigDialog`](#configdialog) below)
* Handles access to the backing dictionary and its contents, including lazily evaluated defaults with `get_or_default`.
  * For ease of access, we use Python `properties` to add/access configuration entries within the `_backing_dict` dictionary.
* Ensures configuration values are saved and loaded correctly throughout CART's runtime.

### `ConfigDialog`

An abstract QT Dialog class which provides common utilities for interacting with a bound `DictBackedConfig` instance. You should subclass this to build the GUI yourself, but doing so provides you the following for free:

* Standardized set of "reset", "confirm", and "cancel" buttons.
* "Are you sure?" confirmation prompt if the user tries to cancel out of the dialog with saved changes.
* Implicit synchronization with the state of CART and its current configuration settings.

## Data Handling

The functions within the `data.py` utility provide wrappers for common data I/O operations in Slicer, adjusted to work effectively in the context of CART's iterative framework. Most utilities also follow the "CART Standard Format" when they are parsing a cohort file; this format is detailed below:

### The CART Standard Format

All example tasks provided by CART follow the "CART Standard" for cohort formatting. This standard can be summarized as follows:

* **UID**: Identifies each case with a unique name/label.
  * Each case must have exactly one **UID** column, and it must be named `uid`.
* **Volume**: A filepath to an anatomical image, in NIfTI or NRRD format.
  * Any column with `volume` in its name is treated as a **Volume** column.
  * Each case must have at least one valid **Volume** entry; multiple are allowed as well.
* **Segmentation**: A filepath to a segmentation image, in NIfTI or NRRD format. 
  * Any column with `segmentation` in its name is treated as a **Segmentation** column.
  * Each case can have none, one, or multiple **Segmentation** entries.
* **Markup**: A filepath to a Slicer Markup JSON file. 
  * Any column with `markup` in its name is treated as a **Markup** column.
  * Each case can have none, one, or multiple **Markup** entries.

If you want your data unit to follow this standard (and load each column according to its detected type automatically), you can subclass the `CARTStandardUnit` to do so. If you want to follow the standard, but handling the loading of each file yourself, you can instead use the `parse_volumes`, `parse_segmentations`, and `parse_markups` functions to identify Volume, Segmentation, and Markup columns, respectively.

### Manual I/O Handling

If your Task needs your cohort to not follow the CART Standard Format, you should still consider using the following I/O utilities for reading/writing common file types. Most are wrappers for common Slicer I/O operations, modified (or with additional checks) to ensure they will run nicely within CART's iterative framework.

#### Volume I/O

Volumes can be loaded in any format currently supported by Slicer (except DICOM, due to its folder-based structure) via the `load_volume` function. Currently only supports saving volumes to _NiFTI_ format with `save_volume_to_nifti`.

#### Segmentation I/O

Like volumes, can load any format supported by Slicer. Can be loaded as a "label" (via `load_label`) or a "segmentation" (via `load_segmentation`). Label files are saving identically to volumes (with `save_volume_to_nifti`), with segmentations being saved using `save_segmentation_to_nifti` instead.

You can also create a "blank" segmentation using the `create_empty_segmentation_node` function; this can be useful for tasks where you want the user to create a segmentation themselves, rather than edit an existing one.

#### Markups I/O

Supports markups stored in both the `.mrk.json` and `.nii` formats. While both formats can be loaded with `load_markups`, markups have two save functions: `save_markups_to_json` (which saves the markups in Slicer's `.mrk.json` format) and `save_markups_to_nifti` (which saves the markups into `.nii` label file format).

For the `.mrk.json` format, what is loaded/saved depends on the type of markup contained within the file; see [the official documentation](https://slicer.readthedocs.io/en/latest/user_guide/modules/markups.html) for more details.

The `.nii`, being a [NiFTI](https://nifti.nimh.nih.gov/nifti-1/) based format, comes with several limitations:

  * Can only store positional point lists.
  * Label information for each point is not conserved in the `.nii` file; instead, it is saved in the `.json` sidecar, which must be parsed alongside the `.nii` file to point labels.
  * Positions are IJK voxel-bound (that is, all markups must are rounded to the nearest voxel position, and cannot exist outside those positions).
  * Only one point can exist in the same IJK co-ordinate; placing multiple in the same position will result in them over-writing each other.
  * Cannot store label ordering information; `.nii` files loaded using `load_markup` will be organized in the order they were found by `numpy` when finding non-zero label values.

#### Sidecars

Sidecar files are built to store data that can't be stored in the "main" file, but should be both associated with it and readily available. To aid with this, CART provides a suite of JSON sidecar utilities, which can find (`find_json_sidecar_path`), save (`save_json_sidecar`), and load (`load_json_sidecar`) data to a sidecar. 

To use them, provide a path to the file the sidecar should be associated with. In the case of saving, you should also provide the information you want stored, formatted into a dictionary compatible with [Python's `json` library](https://docs.python.org/3/library/json.html).

#### Node Grouping

To make managing each data unit's nodes easier, it's often easier to group them into a single "subject" that is hidden/revealed/deleted when needed (rather than doing so for each MRML node manually). If you have a list/set of nodes you want to group, you can use the `create_subject` to streamline this process.


## Task Registration

The utils in `task.py` are mostly for registering custom CART task's post-initialization. In all likelihood, you will only need the `cart_task` decorate from this utility suite. It should be used to denote which class(es) within a Python file should be registered as valid CART tasks if CART attempts to register the file:

```python
from CARTLib.core.TaskBaseClass import TaskBaseClass
from CARTLib.utils.task import cart_task

@cart_task
MyCoolCustomTask(TaskBaseClass):
    ...
```

## Widgets

The contents of the `widgets.py` file are QT widget elements which fall into one of two classes:

* Existing Slicer widgets re-implemented to work better in the context of CART
* Widgets which interact directly with CART itself in a standardized way

Both can be re-used within your custom tasks as you see fit, or sub-classed further to extend/revise their behaviour.

### Success/Error Prompts

The functions `showSuccessPrompt` and `showErrorPrompt` provide a standardized way to show a success/error message to the user. While our example task's mostly use to this provide confirmation that an attempt to save a file was successful (or not), they can be used for any context where you want the user to know something ran successfully (or not).

### CARTSegmentationEditorWidget

A subclass of Slicer's `qMRMLSegmentEditorWidget`, with its functionality extended to work within the CART context. Specifically:

* The associated shortcuts and binds to the MRML scene are handled correctly as CART iterates through the case load.
* It respects changes to the `HideFromEditors` attribute for nodes post-init, unlike the original base class. This allows nodes to be "hidden" on the fly (which CART often does to "cache" data units without removing them from Slicer's memory)

However, please note the following differences from the original widget:

* It does not provide actions in its drop-downs, like those seen in the original subclass
* The `refresh` function is required for it to update its state to match changes in the MRML scene; you should do this automatically within the corresponding task after a new data unit is received to ensure it is properly synchronized.
