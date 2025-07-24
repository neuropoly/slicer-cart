# Segmentation Review and Correction

This task allows for iterative review (and, if needed, correction) of image segmentations for a dataset.

## Cohort Structure

A "case" for this task requires 3 columns:

* `uid`: A unique identifier to "label" the case by. Used throughout the GUI to denote the current case
* `volume`: The volume (in NIfTI or NRRD format) from which the to-be-reviewed segmentation was derived
* `segmentation`: The segmentation (in NIfTI or NRRD format) to be reviewed.

## Task Overview

On task initialization, you will be prompted to select an output directory; this is where the corrected segmentation files will be placed when you click "save" (alongside a `.json` sidecar denoting that you did so, using this tool, and when). Once a valid directory is selected, you can begin iterating through the cases using the `Next` and `Previous` buttons at the top of the GUI.

If you wish to modify the loaded segmentation, simply use the editing widget to select your preferred tool, make your desired edits, and click the `save` button at the bottom of the page. Note that, currently, your changes will _**NOT**_ be auto-saved if you change to a different case after making edits; be careful!
