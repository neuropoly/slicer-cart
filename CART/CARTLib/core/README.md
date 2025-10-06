# CART Core Components

The files within this directory contain the components that nearly (if not all) tasks within CART will use. This includes cohort management, data unit creation and iteration, Slicer layout handing, and the Abstract Base Classes (ABCs) that all tasks and their data units should inherit from.


## Table of Contents

## Table of Contents

* [Cohort Generation](#cohort-generation)
* [Data Management](#data-management)
* [Slicer Layout Handling](#slicer-layout-handling)
  * [The Orientation Flag](#the-orientation-flag)
  * [`LayoutHandler`](#the-layouthandler)
* [Task Creation](#task-creation)

## Cohort Generation

`CohortGenerator.py` holds code responsible for automatically generating cohort files based on the contents of a directory. There is realistically no need to subclass or override any code within this file as a user, but it is made available for reference purposes.

Currently only supports BIDS-like datasets, but will be expanded to support other data structures soon!

## Data Management

`DataManager.py` and `DataUnitBase.py` define how cases are iterated and loaded, respectively. If you are making your own custom task(s), you don't need to worry about the contents of `DataManager.py`; instead, just subclass the `DataUnitBase` class to implement any data loading functionality you would like, and return the resulting class as part of your task's `getDataUnitFactories` function.

## Slicer Layout Handling

The contents of `LayoutManagement.py` are for handling how the nodes in a given case should be displayed to the user in the Slicer viewer. For the most part, CART handles this for you (via a unified orientation selection widget and `LayoutHandler` instance), but you can interact with and/or subclass each of these to enable customized layouts for your task (see [Task Creation](#task-creation) below).

### The Orientation Flag

This enum is used by CART to track what orientation(s) you want to be displayed to the user. It can be one of three "base" values:

* `AXIAL`: Represents the Axial plane
* `SAGITTAL`: Represents the Sagittal plane
* `CORONAL`: Represents the Coronal plane

The `Orientation` enum is a [flag-type enum](https://docs.python.org/3/library/enum.html#enum.Flag); this allows us to "combine" orientations using the `|` operator. The resulting orientations are then treated as all the "base" orientations used to create it:

```python
>>> axial_and_coronal = Orientation.AXIAL | Orientation.CORONAL
>>> print(Orientation.AXIAL in axial_and_coronal) 
True
>>> print(Orientation.SAGITTAL in axial_and_coronal)
False
```

These "combined" orientations are used by the LayoutHandler (detailed below) to denote when the user wants multiple orientations displayed simultaneously; it is not bound to that use, however, and can be re-used in your own tasks as you see fit.

### The `LayoutHandler`

The `LayoutHandler` class is responsible for determining the best layout to display the set of volume nodes (and, by extension, their associated segmentation and markups). By default, CART creates one itself and relies on it to generate new layouts for each data unit (or change the existing layout to match the users preference). This default handler relies on three things to accomplish this:

* A set of volume nodes that it should make displays for.
* A "primary" volume node; this is used as the reference for the purposes of determining where overlays (segmentations and markups) will be displayed. 
  * If none is provided, the first segmentation node is used.
* An `Orientation` flag, containing the view orientation(s) that should be displayed.

It can then "apply" its layout to the Slicer scene; for the default handler, this results in 1 panel per combination of volume node and orientation (Axial, Sagittal, and/or Coronal). 

You can change the orientation post-init with the `set_orientation` function; this invalidates the current layout XML, and will require it be re-applied manually for the changes to take effect in Slicer.

## Task Creation

The basis of any custom task's you want to implement. To ensure compatability with CART, ensure that all logic and GUI elements are placed within a subclass of the `TaskBaseClass` abstract class. If you are using a modern IDE, it should then ask you to implement a number of methods; the requirements of each method are detailed in their respective function documentation. 

A rough guide for what needs to be done can be found below:

* Define how the contents of a cohort case should be parsed, and the results loaded into Slicer, via defining at least one `DataUnitFactory` and returning it with the class's `getDataUnitFactories`.
  * The easiest way to create a `DataUnitFactory` is to subclass the `DataUnitBase` class (discussed in [Data Management](#data-management)) and place it within the map.
* Ensure any GUI elements are built and connected within the `setup` function of your class.
* Determine how the task should synchronize/update itself when a new case is loaded through the `recieve` function.
* Define how the task's contents should be saved when requested (either by the user explicitly saving, or when one of CART's auto-saving methods is applied)
* If your tasks do anything which should be handled when Slicer starts CART with your task loaded, unloads the CART module, or when Slicer is about to close, you should override the `enter`, `exit`, and `cleanup` methods, respectively.