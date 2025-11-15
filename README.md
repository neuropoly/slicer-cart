# Case Annotation and Review Tool (CART)

## Table of Contents

* [What is CART?](#what-is-cart)
* [For Users](#for-users)
  * [Setting up CART](#setting-up-cart)
  * [Getting Started](#getting-started)
  * [Starting a Task](#starting-a-task)
* [For Developers](#for-developers)
  * [Project Standards](#project-standards)
  * [IDE Set Up](#ide-set-up)
  * [Example Data](#example-data)

---

# What is CART?

CART is a module for 3D Slicer designed to help implement, manage, and run iterative analyses on image datasets. You can think of CART as an assembly line for data analysis; you define how your data should be grouped ("cases"), and what process you want to apply to it ("tasks"), and CART tracks how many you've completed and ensures that each has been processed by the task sequentially.

Currently, it provides the following capabilities:

* Managing sequential cases (be they patients, sub-studies, or other collections of data).
* Caching and memory management.
* User profiles (to distinguish between different local users of CART analyses)

A number of features are currently in progress as well, and will be available upon CART's full release:

* Custom task creation and registration.
* Case pre-fetching/deferred loading.
* Per-user + per-task configurations.

---

# For Users

## Setting up CART

### Prerequisites

- Slicer v5.8 (other versions might work, without guarantee)

### Installation

Clone this repository somewhere you can easily access it. You can do this one of two ways:

1. Downloading the repository from GitHub:
   1. Download the ZIP folder from [here](https://github.com/SomeoneInParticular/CART/archive/refs/heads/main.zip)
   2. Wait for the download to complete 
   3. Once complete, navigate to the `CART-main.zip` file and unzip it (on most OS systems, double-clicking on the file should tell you how to do this)

2. Cloning the repository via `git`:
   1. Open a terminal in a directory of your choice
   2. Run the following command to clone the current `CART` repository:
    ~~~
    git clone git@github.com:SomeoneInParticular/CART.git CART-main
    ~~~

### Registering CART in Slicer

0. Open a file browser window and navigate to the downloaded `CART-main` directory. Then, navigate to the `CART` subdirectory, which should contain a `CART.py` file.
1. Start up Slicer
2. Select `Edit` (top left) > `Application Settings`
<img width="1066" height="154" alt="image" src="https://github.com/user-attachments/assets/1f2c4d4f-ce10-46fd-8165-09c0df87a7e6" />

3. In the "settings" popup, select `Modules` from the left sidebar
<img width="865" height="650" alt="image" src="https://github.com/user-attachments/assets/ea9d4013-b77b-47ef-84b5-f4d38fd7f044" />

4. Click and drag `CART.py` from the file browser into the "Additional module paths" panel.
5. Click "OK"; Slicer should prompt you that it needs to restart. Say "Yes".

### [Optional] Setting CART as your Default Module

1. Start Slicer
2. Select `Edit` (top left) > `Application Settings`
3. In the "settings" popup, select `Modules` from the left sidebar
4. Under "Default startup module", Select `Utilities` > `CART`
<img width="506" height="760" alt="image" src="https://github.com/user-attachments/assets/66a360ff-8ad6-406e-a498-7e1ff1ae6f20" />

### Getting Started

Before you can begin, you need to create a user profile and identify where the files you want to use are located.

#### User Profile

The user profile allows CART to identify who is currently using the program. As well as tracking your configuration settings, the details you provide here can be used by CART to label the result of your analyses for later reference.

To add a new user:

0. Select the `CART` module, if you have not done so already.
1. Next to the "User:" row, select the `+` button.
2. Fill in the details prompted to you by the resulting popup, and click "OK"

If you have already registered yourself, you can select your user-name from dropdown instead.

### Data Selection

This is a path to the directory containing the files you want to. Unless explicitly specified otherwise (via an absolute path), CART will assume all directory references are relative to this directory. Aside from this, the contents of this directory can be in any structure you like (though, in absence of a pre-existing format, we recommend the [BIDS](https://bids-specification.readthedocs.io/en/stable/) format)

To select the Data Path:

0. Select the `CART` module, if you have not done so already.
1. Next to the "Data Path:" row, click the `...` button.
2. Navigate to the desired directory in the resulting pop-up dialog.
3. Click "Choose" to confirm your choice.


## Starting a Task

Once you've specified a user and a data folder, you can run a "task" on the data. This requires selecting the task you want to do, and defining a set of cases you want to run the task on (a "cohort").

### Task

Selecting a Task is simple; simply select the task you want to run from the drop-down menu labelled "Task". By default, CART provides a number of pre-defined tasks for you to use:

* **[Generic Classification](CART/CARTLib/examples/GenericClassification/README.md)**: Rapidly classify cases into user-specific classes, and/or make other remarks about each case.
* **[Rapid Markup](CART/CARTLib/examples/RapidMarkup/README.md)**: Quickly place, move, replace position markups on a case-by-case basis, with custom positional labels being specified by you!
* **[Segmentation Review](CART/CARTLib/examples/SegmentationReview/README.md)**: General purpose segmentation review and correction tool. Specify a "primary" segmentation you want to evaluate, and CART will load it (and anything else you want to reference) into view for you to review, correct, or replace entirely.

In the future, you will also be able to register arbitrary Tasks, either created by you or downloaded from other developers.

### Cohort

The "Cohort" is a set of "cases" you want to apply the task too iteratively. What a "case" entails is largely up to you; it can represent a single patient, a single timepoint, or any other grouping that you desire.

In CART, a cohort (and the cases within it) are managed through a CSV file; one each row (barring the first, being the "header") represents a single case, and each column a resource that case can have.

The only strict requirement of a cohort CSV file is that it must have a `uid` column, and that each case within the dataset have a unique value in this column. CART uses this string to track each case both internally (for iteration) and externally (for output management); as such, please ensure the values for this column are distinct and meaningful to you whenever possible.

Aside from this constraint, it is otherwise up to the Task you selected what resources each case should include. Most Tasks will document these requirements in a README or wiki of some kind. For example, the cohort file for a segmentation review task could look something like this:

```
uid,volume_t2w,segmentation_deepseg
sub-amu05_T2w,sub-amu05/anat/sub-amu05_T2w.nii.gz,derivatives/labels/sub-amu05/anat/sub-amu05_T2w_seg.nii.gz
sub-amu04_T2w,sub-amu04/anat/sub-amu04_T2w.nii.gz,derivatives/labels/sub-amu04/anat/sub-amu04_T2w_seg.nii.gz
...
```

Once you have created an appropriate cohort file for your task, you can select it by:

1. Selecting the `...` button next to the file browser labelled "Cohort File"
2. Navigating to the cohort file in the resulting pop-up
3. Selecting it, and clicking "Choose" to confirm your choice.


> [!NOTE]  
> File resources in a cohort can be absolute OR relative; for the latter, the root path is treated as the path you selected as the [Data Path](#data-selection) during initial CART setup.


### Auto-generating a Cohort File

If your data is organized in a structured format (like BIDS), CART can help you automatically generate the cohort CSV file. This feature becomes available once you have selected a valid **Data Path**.


> [!NOTE]  
> Cohort generation and editing will only be enabled if the [Data Path](#data-selection) points to a "valid" dataset. **Currently, CART only supports pseudo-BIDS compliant datasets. (Datasets containing matching `/derivatives` and `raw` cases | subjects)** 


To launch the generator, click the **"Auto-generate cohort file"** button next to the "Cohort File" selector. If you already have a cohort file selected, this button will change to **"Edit cohort file"**, allowing you to modify it using the same tool.


#### The Generator Interface 

The generator window provides a powerful interface for building your cohort from scratch or editing an existing one.

* **Main Table**: The central view displays your data. Each **row** represents a case (e.g., a subject), and each **column** represents a resource (e.g., a specific image file).
* **Row/Column Toggling**: You can use the checkboxes in the first column and the header row to include or exclude specific cases or entire resource columns from the final saved file.

#### Creating and Filtering Columns

The primary function of this tool is to populate the resource columns by scanning the files within your Data Path. This is done using the "Column Creating, Filtering and Editing" panel.


**To create a new column:**

1.  Ensure the **"Target Column"** dropdown is set to "Create New Column".
2.  In the **"New Column Name"** field, enter a descriptive name for the resource (e.g., `volume_t2w`, `segmentation_prostate`).
3.  Use the **"Filenames MUST Contain"** field to specify unique text that identifies the files for this column. For example, to find T2-weighted images, you might enter `T2w.nii.gz`. You can add multiple comma-separated filters.
4.  Optionally, use the **"Filenames MUST NOT Contain"** field to exclude files that match your inclusion criteria but should be ignored (e.g., `_brain_mask`).
5.  Click the **"Create New Column from Filters"** button. The table will update with a new column populated with the file paths that match your rules.

**Other Management Features:**

* **Edit Filters**: Select an existing column from the "Target Column" dropdown to view and modify its filters.
* **Rename a Column**: **Double-click** on any column header (except `uid`) to rename it.
* **Delete a Column**: Select a column from the "Target Column" dropdown and click the **"Delete Column"** button.

#### Saving Your Cohort

Once you are satisfied with your cohort configuration, click **"Save and Apply"**. The file will be saved inside a `cohort_files` directory within your main Data Path. You can then proceed to select it and run your task. By default, a new file (`cohort.csv`, `cohort1.csv`, etc.) is created, but you can check the **"Override selected Cohort File"** box to save changes to the currently loaded file instead.

### Running the Task

Once you have selected all the parameters prior, click "Confirm" to begin! How CART proceeds past this point depends on the task you selected; see their respective documentation for details.


---

# For Developers:

## Project Standards

Below is a short summary of standards and format we use in CART; for more details, please refer to the [developer wiki](https://github.com/SomeoneInParticular/CART/wiki).

### Python

We follow [PEP8](https://peps.python.org/pep-0008/) standards with two notable exceptions:

* GUI code which directly utilizes or references C++ code (via QT) should use `lowerCamelCase` for functions, rather than the standard `lower_snake_case` used by Python, to help distinguish it from "pure" Python code.
* Line length is capped at 88 characters per line, rather than 79; this is derived from our linter (Black), and you can read the justification [here](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html#line-length)

## IDE Set Up

### Source Directories

As both Slicer and CART load libraries into Python's path post-init, most IDEs will not be able to recognize some of the import statements used by our codebase by default.

To fix this, please mark the following directories as "source" folders in the Project's structure:

* `{Slicer Installation Directory}/bin/Python`: exposes that installations versions of VTK, CTK, and QT, along with slicer's own utilities.
* `{This Directory}/CART`; exposes CARTLib and its contents.

## Example Data

The example data consists of a subset (fold0) from the PI-CAI dataset, featuring prostate MRI images and their corresponding segmentations. The original data can be obtained from the [official website](https://zenodo.org/records/6624726) by downloading the `picai_public_images_fold0.zip` file.

For this project, the first four subjects were selected and the images were converted from MHA to NRRD format.

1. Example `sample_data` is adapted from this original data and is located under `sample_data.zip`.
2. Unzip the file to a folder of your choice.
