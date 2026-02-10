# Segmentation Review and Correction Task

This task allows for iterative review (and, if needed, correction) of image segmentations for a volume. To aid with this, you can load multiple volumes, other reference segmentations, and even file markups on a case-by-case basis as well. You can also use this to generate segmentation manually, should no segmentation exist currently exist for a case in the cohort.

* [Creating a Cohort File](#creating-a-cohort-file)
* [Example Cohort Files](#example-cohort-files)
  * [Segmentation Creation](#segmentation-creation)
  * [Segmentation Review](#segmentation-review)
* [Detailed Cohort Specifications](#detailed-cohort-specifications)

## Cohort File Specification

This task follows the [CART Standard Cohort Specification](https://github.com/SomeoneInParticular/CART/tree/main/CART/CARTLib/utils#the-cart-standard-format)

The cohort file for this task can contain the following column types:

* **UID**: A label each case with a unique name/label. 
  * Only one **UID** column can exist, and it must be named `uid`.
  * Each case must have a valid **UID**.
* **Volume**: A filepath to an anatomical image, in NIfTI or NRRD format.
  * Any column with `volume` in its name is treated as a **Volume** column.
  * Each case must have at least one valid **Volume** entry; multiple are allowed as well.
* **Segmentation**: A filepath to a segmentation image, in NIfTI or NRRD format. 
  * Any column with `segmentation` in its name is treated as a **Segmentation** column.
  * Each case can have none, one, or multiple **Segmentation** entries.
* **Markup**: A filepath to a Slicer Markup JSON file. 
  * Any column with `markup` in its name is treated as a **Markup** column.
  * Each case can have none, one, or multiple **Markup** entries.

Which segmentation for a given case is determined to be the "primary" segmentation (and thus will be the segmentation you can edit and save) is determined as follows:

1. The first (left to right) Segmentation column with a valid filepath with `primary` in its name is chosen.
2. Failing that, the first Segmentation column with a valid filepath is chosen
3. If that fails, then the task assumes you want to _create_ a new segmentation, and generates a "blank" segmentation in Slicer instead.

Some examples of valid cohort files (and how they will be loaded into CART) are provided below for your reference.

# Example Cohort Files

Below are examples of valid cohort files for common use cases. 
The file names used are placeholders representing a BIDS-like dataset; while this structure is encouraged, it is not required.

## Segmentation Creation

Only requires one (or more) volume columns to segment. You may optionally provide some markups as well.

### Single Volume
    
| uid     | volume_T2w                      |
|---------|---------------------------------|
| sub_001 | sub_001/anat/sub_001_T2w.nii.gz |
| sub_002 | sub_002/anat/sub_002_T2w.nii.gz |

### Multi-volume (T2w-Based Reference Orientation)

| uid     | volume_T2w                      | volume_T1w                      |
|---------|---------------------------------|---------------------------------|
| sub_001 | sub_001/anat/sub_001_T2w.nii.gz | sub_001/anat/sub_001_T1w.nii.gz |
| sub_002 | sub_002/anat/sub_002_T2w.nii.gz | sub_001/anat/sub_002_T1w.nii.gz |

### Multi-volume (T1w-Based Reference Orientation)

[Note the change in column order]

| uid     | volume_T1w                      | volume_T2w                      |
|---------|---------------------------------|---------------------------------|
| sub_001 | sub_001/anat/sub_001_T1w.nii.gz | sub_001/anat/sub_001_T2w.nii.gz |
| sub_002 | sub_002/anat/sub_002_T1w.nii.gz | sub_001/anat/sub_002_T2w.nii.gz |

### Single Volume (w/ Markup Reference)

| uid     | volume_T2w                      | markup_discs                                |
|---------|---------------------------------|---------------------------------------------|
| sub_001 | sub_001/anat/sub_001_T2w.nii.gz | derivatives/sub_001/anat/sub_001_discs.json |
| sub_002 | sub_002/anat/sub_002_T2w.nii.gz | derivatives/sub_002/anat/sub_002_discs.json |

## Segmentation Review

You can also correct the reviewed segmentations in the editor, as desired.

### Single Volume, Reviewing a Liver Segmentation
    
| uid     | volume_T2w                      | segmentation_liver                            |
|---------|---------------------------------|-----------------------------------------------|
| sub_001 | sub_001/anat/sub_001_T2w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz |
| sub_002 | sub_002/anat/sub_002_T2w.nii.gz | derivatives/sub_002/anat/sub_002_liver.nii.gz |

### Single volume, Reviewing a Liver Segmentation (w/ Kidney Segmentation for Reference)

| uid     | volume_T2w                      | primary_segmentation_liver                    | segmentation_kidney                            |
|---------|---------------------------------|-----------------------------------------------|------------------------------------------------|
| sub_001 | sub_001/anat/sub_001_T2w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz | derivatives/sub_001/anat/sub_001_kidney.nii.gz |
| sub_002 | sub_002/anat/sub_002_T2w.nii.gz | derivatives/sub_002/anat/sub_002_liver.nii.gz | derivatives/sub_002/anat/sub_002_kidney.nii.gz |

### Multi-volume (w/ T2w as orientation reference), Reviewing a Liver Segmentation (w/ Kidney Segmentation as Reference)
    
| uid     | volume_T2w                      | volume_T1w                      | primary_segmentation_liver                    | segmentation_kidney                            |
|---------|---------------------------------|---------------------------------|-----------------------------------------------|------------------------------------------------|
| sub_001 | sub_001/anat/sub_001_T2w.nii.gz | sub_001/anat/sub_001_T1w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz | derivatives/sub_001/anat/sub_001_kidney.nii.gz |
| sub_002 | sub_002/anat/sub_002_T2w.nii.gz | sub_002/anat/sub_002_T1w.nii.g  | derivatives/sub_002/anat/sub_002_liver.nii.gz | derivatives/sub_002/anat/sub_002_kidney.nii.gz |

### Multi-Volume (w/ T2w as Orientation Reference), Reviewing a **Kidney** Segmentation (w/ **Liver** Segmentation as Reference) 

[Note the change in column names]
    
| uid     | volume_T2w                      | volume_T1w                      | segmentation_liver                            | primary_segmentation_kidney                    |
|---------|---------------------------------|---------------------------------|-----------------------------------------------|------------------------------------------------|
| sub_001 | sub_001/anat/sub_001_T2w.nii.gz | sub_001/anat/sub_001_T1w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz | derivatives/sub_001/anat/sub_001_kidney.nii.gz |
| sub_002 | sub_002/anat/sub_002_T2w.nii.gz | sub_002/anat/sub_002_T1w.nii.g  | derivatives/sub_002/anat/sub_002_liver.nii.gz | derivatives/sub_002/anat/sub_002_kidney.nii.gz |

### Multi-Volume (w/ T2w as Orientation Reference), Reviewing a liver Segmentation (w/ Kidney Segmentation and Vein Lines for Reference):

| uid     | volume_T2w                      | volume_T1w                      | segmentation_liver                            | primary_segmentation_kidney                    | markup_veins                                |
|---------|---------------------------------|---------------------------------|-----------------------------------------------|------------------------------------------------|---------------------------------------------|
| sub_001 | sub_001/anat/sub_001_T2w.nii.gz | sub_001/anat/sub_001_T1w.nii.gz | derivatives/sub_001/anat/sub_001_liver.nii.gz | derivatives/sub_001/anat/sub_001_kidney.nii.gz | derivatives/sub_001/anat/sub_001_veins.json |
| sub_002 | sub_002/anat/sub_002_T2w.nii.gz | sub_002/anat/sub_002_T1w.nii.g  | derivatives/sub_002/anat/sub_002_liver.nii.gz | derivatives/sub_002/anat/sub_002_kidney.nii.gz | derivatives/sub_001/anat/sub_002_veins.json |

# Detailed Cohort Specifications

A more details breakdown of the cohort specification, and how it translates to Slicer and CART's use of the case's contents, is as follows:

* `uid`: Single column
* `volume`: Any column with `volume` in its name (`volume_T1w`, `rescan_volume` etc.) is treated as a standard imaging sequence.
  * Each case must have at least one valid `volume` column entry. 
  * If multiple `volume` columns are specified, each volume will be displayed in its own column in the Slicer viewer.
  * Cases lacking an entry for a given `volume` column are ignored.
  * The first _valid_ `volume` column for each case is used as the reference volume.
* `segmentation`: Any column with `segmentation` in its name (`segmentation_deepseg`, `dr_johns_spinal_segmentation` etc.) is treated as a segmentation label, as is loaded as an overlay on top of _all_ volumes.
  * The to-be-reviewed segmentation is determined by a few criterion.
    * If the column has `primary` in its name (i.e. `primary_segmentation`, `deepseg_segmentation_primary`), it is selected as the "to-be-reviewed" segmentation, making it the default target for any corrections made.
    * If multiple `primary` columns exist, the first valid on for a given case is selected.
    * If no valid `primary` columns exist, the first valid segmentation is selected.
    * If a case lacks any valid `segmentation` column entries whatsoever, we assume you want to create the corresponding segmentation instead.
  * You do **_not_** need to specify any `segmentation` columns; doing so will assume you are creating the corresponding segmentations instead.
* `markup`: Any column with `markup` in its name is loaded as [Slicer Markup file](https://slicer.readthedocs.io/en/latest/user_guide/modules/markups.html).
  * **Currently Experimental:** markups are loaded in for reference only. We cannot guarantee any consistency with how they will behave it edited, deleted, or created post-load; this task only loads markups relevant to the currently selected case, and hides those which are not.
  * Act identically to `segmentation` columns, except that they cannot be edited at all, and no "primary" markup is selected.