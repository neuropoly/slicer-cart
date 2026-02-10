# Generic Classification

This task is designed to allow for rapid classification of subjects, sequences, or other sets of radiological data.

## Cohort File Specification

This task follows the [CART Standard Cohort Specification](https://github.com/SomeoneInParticular/CART/tree/main/CART/CARTLib/utils#the-cart-standard-format)

# Using this Task

## Setup

When initially starting up, you will be prompted to select an output directory. This is where the CSV containing the classifications of each case will be placed, along with a JSON sidecar tracking the name of each class and their description (if any).

If you selected a directory which does not already have these files, you will need to add these classes yourself. To do so:

1. Click the "Add New Class" button, to the upper left of the "Classifications" list (which will currently be empty).
2. Fill in the name the new class should have in the resulting prompt
   * This label will be what is displayed in the "Classifications" list, as well as the label saved to the CSV for cases which are classified using it.
3. Optionally, add a description of the class.
   * This will become a tooltip for label in the "Classification" list, as well as the description saved to the sidecar file when a case is saved.
4. Select "OK" to confirm.

## Classifying a Case

Once you have a set of potential classes to choose from, simply click the checkbox to the right of each class to "mark" the case as being that class. You can select one, multiple, or no classes for each case.

Optionally, you may also add miscellaneous notes by typing in "Other Remarks" section, placed below the "Classifications" list. Anything placed here will also be saved in the output CSV for later reference, alongside the classifications you selected in the previous step. 

# Configuration

This task currently has no configuration options. If you have a suggestion for configurable options you would like to have, please open an issue on this GitHub repository, and we will look into their implementation as soon as we can!
