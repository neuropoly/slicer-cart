# Rapid Markup Task

This task streamlines the placement of markup labels into a given case, while still allowing the user to determine what those labels are and the order they should be placed in.

# Creating a Cohort File

This task follows the [CART Standard Cohort Specification](../../utils/README.md#the-cart-standard-format)

# Using the Task

## Setup

Add the labels you want to place to the "Markup Labels" list. For each label:

1. Click the "Add" button, to the bottom left of the task panel.
2. Type in the label name in the resulting prompt
3. Click "Ok"

## Placing a Label

To place a specific label, or move its existing placement to a new position:

1. Select the label you want to place
2. Click the "Begin Placement" button
3. Click on the location in the viewer where the label should be placed

# Configuration

## Start Automatically

If the "Start Automatically" option is checked, CART will initiate markup placement for the first unplaced markup label (if available) it finds in the markup label list when a case is loaded.

## Chained Placement

If the "Chain Placements" option is checked, CART will start markup placement for the next unplaced label (if one exists) each time you place the current markup label, until none remain. Right click to skip over the currently selected label.

## Deletion Management

If the "Deletions Remove Corresponding Markup" option is checked, deleting a markup label will also delete the corresponding markup placed in the viewer. If not, the markup in the viewer will remain, but will no longer be "tracked" by the Task.
