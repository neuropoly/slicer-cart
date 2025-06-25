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

The example data is a subset, fold0, of the PI-CAI dataset, which is a collection of prostate MRI images and their corresponding segmentations.
1. Go to the [provided website](https://zenodo.org/records/6624726)
   and download the `picai_public_images_fold0.zip` file.
2. Unzip the file to a folder of your choice.


