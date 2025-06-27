# Generic Iterator Project Plan 

## Basic Stucture

- **CARTLib**: The main library containing the base classes for defining the standard iterator and Task Workflow.
- **CARTLib/Task**: Contains the base classes for defining a Task.
  - A task is defined as an actionable set of steps that can be taken by a specific user.
  - Tasks Do not load data they are only used to define the GUI and support the user in performing a specific action.
  - Tasks are at the "DataUnit" level, meaning that they are specific to a single DataIO object 
    (e.g. a single row in the cohort csv).
- **CARTLib/DataIO**: Contains the base classes for defining a DataIO.
  - DataIO is used to interface with the cohort csv(Which is an organizational scheme we required to be defined by the user beforehand).
  - DataIO baseclass is used to map a single row of the cohort csv to loaded Slicer Nodes and vice versa.
  - DataIO is used to load the data and save the data.
  - DataIO is used to define the data that is loaded and saved for a specific task.
  - DataIO is at the "DataUnit" level, meaning that it is specific to a single DataIO object 
    (e.g. a single row in the cohort csv).
- **CARTLib/DataManager**: Contains the base classes for defining a DataManager.
  - DataManager is used to interface/ convert the Cohort csv to a list of DataIO objects.
  - DataManager is used to manage the loading and saving of data for a specific 'project' or set of tasks.
  - DataManager is at the "Project" level, meaning that it is specific to a set of tasks and DataIO objects.
  - It is used to create the DataUnits
- **CARTLib/TaskConfig**: Contains the base classes for defining a TaskConfig.
  - TaskConfig is used to define all of the hyperparameters and configurations for a specific 'project' or set of tasks 

Logical Extensions: 
- **CART/SegmentationTask**: A specific task for segmentation. 
- **CART/ClassificationTask**: A specific task for classification.
- **CART/ReviewTask**: A specific task for reviewing existing segmentations or classifications."
- **CARTLib/TaskWorkflow**: Contains the base classes for defining a TaskWorkflow.
- **CARTLib/TaskConfigMaker**: Contains the base classes for defining a TaskWorkflowManager.
- **CARTLib/CSVCohortMaker**: Contains the base classes for defining a CSVCohortMaker.


---
# Example Data
The example data consists of a subset (fold0) from the PI-CAI dataset, featuring prostate MRI images and their corresponding segmentations. The original data can be obtained from the [official website](https://zenodo.org/records/6624726) by downloading the `picai_public_images_fold0.zip` file. 
For this project, the first four subjects were selected and the images were converted from MHA to NRRD format.

1. Example `sample_data` is adapted from this original data and will be located under `sample_data.zip`.
2. Unzip the file to a folder of your choice.


----

# BUGS
-[ ] Mix multiScene support and rm the explicit "clearScene" that is currently triggered on the "Next"/"Previous" button.
-[ ] The input of new raters updates the CODE's configuration.json. This is not the desired behavior, as the configuration should be copied from the original CODE and not modified.
- 