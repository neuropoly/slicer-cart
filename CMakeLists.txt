cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(CART)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/CART")
set(EXTENSION_CONTRIBUTORS "Kalum Ost (Montréal Polytechnique), Kuan Li (Montréal Polytechnique), Ivan Johnson-Eversoll (University of Iowa)"),
set(EXTENSION_DESCRIPTION "This is an project trying to unify and standardize the common functionaility of 'Case' itterators such as SlicerCart, mpReview, CaseIterator, and many more non published projects. ")
set(EXTENSION_ICONURL "https://www.example.com/Slicer/Extensions/CART.png")
set(EXTENSION_SCREENSHOTURLS "https://www.example.com/Slicer/Extensions/CART/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(CART)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
