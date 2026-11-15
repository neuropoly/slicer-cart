# Correcting SCT Outputs with CART

You can use CART instead of [manual-correction](https://github.com/spinalcordtoolbox/manual-correction) to fix segmentations and labels from the [Spinal Cord Toolbox (SCT)](https://spinalcordtoolbox.com).

Before you start, install CART in Slicer ([see here](https://neuropoly.github.io/slicer-cart/#installing-cart)).

## 1. Make a Cohort File

Make a `.csv` file with one row per subject. SCT can make it for you (see [spinalcordtoolbox#5091](https://github.com/spinalcordtoolbox/spinalcordtoolbox/issues/5091)), or you can write it yourself:

```
uid,T2w_volume_reference,seg-manual_segmentation_editable,labels-disc-manual_markup_editable
sub-01,/data/sub-01/anat/sub-01_T2w.nii.gz,/sct/sub-01_T2w_seg.nii.gz,/sct/sub-01_T2w_labels-disc.nii.gz
sub-02__ses-01,/data/sub-02/ses-01/anat/sub-02_ses-01_T2w.nii.gz,/sct/sub-02_ses-01_T2w_seg.nii.gz,/sct/sub-02_ses-01_T2w_labels-disc.nii.gz
```

* `uid` is the subject. If there is a session, write `sub-XX__ses-YY` (two underscores).
* Put the image in a column ending with `_volume_reference`.
* Put segmentations in columns ending with `_segmentation_editable`, and disc labels in columns ending with `_markup_editable`.
* The first part of the column name (like `seg-manual`) goes at the end of the saved file name.
* The files can be in any folder. You don't need a `.json` file next to the `.csv`.

## 2. Open it in CART

```
Slicer --python-code "import CART; CART.open_cohort(r'/path/to/cohort.csv', 'Segmentation', r'/path/to/dataset/derivatives/labels')"
```

Use `'Segmentation'` for segmentations and `'Markup'` for disc labels. The first time, CART asks you to make a profile. Your name is saved with each correction.

## 3. Fix Each Subject

* **Segmentations**: pick the segmentation in CART's panel and fix it with the tools under it.
* **Disc labels**: drag a label to move it. Right-click it to delete it. To add a missing disc, place a new point and rename it to the disc number (like `6`) in Slicer's Markups module. CART saves that number in the file.

Press `Alt+D` to save and go to the next subject. Press `Alt+S` to only save.

## 4. Find the Results

Your corrections are saved in the output folder, in BIDS format. Each one comes with a `.json` file with your name and the date:

```
derivatives/labels/sub-01/anat/sub-01_T2w_seg-manual.nii.gz
derivatives/labels/sub-01/anat/sub-01_T2w_seg-manual.json
```

The files keep the same orientation as the original image. Disc labels keep their numbers. Your SCT files are never changed.
