The Files here were taken directly from the SlicerCaseIterator module developed by the great Joost van Griethuysen

The goal of this project is
to create a unified code base for a configurable 3D Slicer extension that can be used for manual segmentation,
classification, and review tasks and any other tasks that can be defined by the user.

These files were added for reference while creating the new set of base classes for the new CART module.


[LayoutLogic.py](LayoutLogic.py) -- This is a great logic file that we can adapt to our needs. I think this is going to be required to interface with the "taskConfig" and define any "Hanging Protocols"

[SegmentationBackend.py](SegmentationBackend.py) -- This is a starting point for defining the new genric "Task" base class. And one of the first goals of this is to recreate the functionality of this file using the new base classes.
