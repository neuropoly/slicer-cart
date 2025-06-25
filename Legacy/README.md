The submodules within this directory were precursors to the project; our goal was to unify their functionality into a single "main" iterator tool that could be used (or extended) to manage any annotation/review workflow. These tools include:

* [SlicerCaseIterator](https://github.com/JoostJM/SlicerCaseIterator): Module by the great Joost van Griethuysen. Was designed to handle the loading and saving of segmentations within a dataset automatically, allowing the user to focus on segmenting each patient one-by-one.
* [SlicerUltrasound](https://github.com/SlicerUltrasound/SlicerUltrasound/tree/main): Specifically the `AnnotateUltrasound` submodule, whose UI was the basis for our own.

Assuming you have already initialized the `git` repository, you can download the reference copy of these repositories by running the following (replacing `<module_name>` with the name of the module you want to clone):

```bash
# Initialize the submodule manager
git submodule init
# Pull the module you want (omit a module name to pull them all)
git submodule pull <module_name>
```

Some specific files of note:

[(SlicerCaseIterator) LayoutLogic.py](SlicerCaseIterator/SlicerCaseIteratorLib/LayoutLogic.py) -- This is a great logic file that we can adapt to our needs. I think this is going to be required to interface with the "taskConfig" and define any "Hanging Protocols"

[(SlicerCaseIterator) SegmentationBackend.py](SlicerCaseIterator/SlicerCaseIteratorLib/SegmentationBackend.py) -- This is a starting point for defining the new genric "Task" base class. And one of the first goals of this is to recreate the functionality of this file using the new base classes.

[(SlicerUltrasound) AnnotateUltrasound.ui](SlicerUltrasound/AnnotateUltrasound/Resources/UI/AnnotateUltrasound.ui) -- The UI file for the annotator, which was used for the basis of our own.