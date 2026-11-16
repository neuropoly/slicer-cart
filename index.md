---
title: Home
layout: default
---

# Case Annotation and Review Tool (CART)

<img src="./resources/icon.png" width="150">

# What is CART?

CART is a module for 3D Slicer designed to help implement, manage, and run iterative analyses on image datasets. You can think of CART as an assembly line for data analysis; you define how your data should be grouped ("cases"), what should be loaded for you ("resources"), and what process you want to apply to it ("tasks"), and CART will manage the rest for you! Most tasks will even track how many you've completed, ensuring that you don't repeat the same case twice (or skip over one by mistake).

Currently, it provides the following capabilities:

* Managing sequential cases (be they patients, sub-studies, or other collections of data)
* Automatic caching and memory management (including recent case caching)
* Defining and handling multiple jobs, which can be run independently of one another
* Several common tasks out-of-the-box, including:
  * Segmentation Review, Creation, and Correction
  * Markup Management and Review
  * Case Classification and Modification

Developers can also extend its capabilities further, creating custom tasks (with their own custom UI elements) that still hook into CART's case-based iteration and memory management utilities!

# Frequently Asked Questions (FAQ)

WIP

# For Developers

WIP

# Contributors

Original idea and first version of code from Dr. Laurent Létourneau-Guillon and his team in ICH_SEGMENTER_V2, SlicerCART, and Brain_Extraction. This is an effort to create a unified code for a configurable 3D Slicer extension.

Contributors include:
- Kalum Ost
- Laurent Létourneau-Guillon
- Emmanuel Montagnon
- An Ni Wu
- Maxime Bouthillier
- Delphine Pilon
- Julien Cohen-Adad