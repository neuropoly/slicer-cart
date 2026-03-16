import itertools
from datetime import datetime
import json
from functools import singledispatch
from pathlib import Path
from typing import Optional, Any, Callable

import numpy as np

import slicer
import vtk

from CARTLib.core.DataUnitBase import DataUnitBase
from CARTLib.utils.config import MasterProfileConfig, JobProfileConfig
from CARTLib.core.LayoutManagement import Orientation, LayoutHandler


## LOADING ##
def load_volume(path: Path):
    """
    Load a file into Slicer as a Volume.

    Unlike slicer's default utility function, it will hide the volume from view
    by default to better work with CART's iterative DataUnit loading.

    :param path: Path to the file
    """
    # Load the file into a volume node, hidden from view
    return slicer.util.loadVolume(path, {"show": False})


def load_label(path: Path):
    """
    Load a file into Slicer as a LabelVolume.

    Unlike slicer's default utility function, it will hide the label from view
    by default to better work with CART's iterative DataUnit loading.

    :param path: Path to the file
    """
    # Load the file into a label node, hidden from view
    return slicer.util.loadLabelVolume(path, {"show": False})


def load_segmentation(path: Path):
    """
    Load a file into Slicer as a Segmentation.

    Unlike slicer's default utility function, it will hide the segmentation from
    view by default to better work with CART's iterative DataUnit loading.

    :param path: Path to the file
    """
    # We first have to load it as a label volume
    label_node = load_label(path)

    # Then pass its contents to a segmentation node
    scene = slicer.mrmlScene
    segment_node = scene.AddNewNodeByClass("vtkMRMLSegmentationNode")
    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
        label_node, segment_node
    )

    # Hide it from view by default
    segment_node.SetDisplayVisibility(False)

    # Remove the (now redundant) label node from the scene
    scene.RemoveNode(label_node)
    del label_node

    # Return the result
    return segment_node


def load_markups(path: Path) -> list[slicer.vtkMRMLMarkupsFiducialNode]:
    # If the path points to a NiFTI file, load it using our custom loader
    if ".nii" in path.suffixes:
        return [load_nifti_markups(path)]
    # Otherwise, assume it's a native Slicer format
    return load_slicer_markups(path)


def load_slicer_markups(path: Path) -> list[slicer.vtkMRMLMarkupsFiducialNode]:
    """
    Loads a markup from a file which is in an official Slicer
    format (.json or .csv).

    If you are loading a points list from a NiFTI file,
    you should use `load_nifti_markups` instead.

    Note that, due to a mismatch between Slicer's documentation and
    its actual behaviour when loading markups from a file containing
    multiple markup sets, we have implemented a workaround to make it
    "act" as documented instead. Hopefully this will be fixed in
    upcoming Slicer releases, though!
    """
    # Find all fiducial nodes already loaded into the scene
    all_fiducials = set(slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"))

    # THIS IS SUPPOSED TO RETURN A LIST IF THERE ARE MULTIPLE COMPONENTS IN THE FILE
    # IT DOES NOT https://slicer.readthedocs.io/en/latest/developer_guide/slicer.html#slicer.util.loadMarkups
    markups_nodes = slicer.util.loadMarkups(
        path
    )
    # If none were found, raise an error
    if markups_nodes is None:
        raise ValueError(f"Failed to load markups from {path}")
    # If there was only one markup, wrap it in a list for easier handling
    if not isinstance(markups_nodes, list):
        markups_nodes = [markups_nodes]

    # Find all fiducials that aren't loaded yet
    all_new_fiducials = list(
        set(slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")) - all_fiducials
    )
    print(f"Found {len(all_new_fiducials)} new markups nodes after loading {path}")
    print(f"New markups in the scene: {[node.GetName() for node in all_new_fiducials]}")

    # If Slicer quietly loaded a fiducial without returning it to us,
    # catch it and warn the user that this happened.
    if all_new_fiducials != markups_nodes:
        print(
            "Warning: The loaded markups returned from `slicer.util.loadMarkups` "
            "does not match the expected set of new markups."
        )
        difference = set(markups_nodes) - set(all_new_fiducials)
        if difference:
            print(f"Unexpected Nodes: {[node.GetName() for node in difference]}")
        markups_nodes = all_new_fiducials

    print(f"Markups nodes: {[node.GetName() for node in markups_nodes]}")

    # Hide all the new markup nodes from view by default
    for markups_node in markups_nodes:
        displayNode = markups_node.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(False)

    return markups_nodes


NIFTI_SIDECAR_LABELS_KEY = "Labels"


def load_nifti_markups(path: Path) -> slicer.vtkMRMLMarkupsFiducialNode:
    """
    Loads a set of markups from a NiFTI style binary label set.

    Note that markups stored in NiFTI cannot support overlapping markup positions!
    As well, NiFTI cannot natively save the label names for each value within it;
    we work around this via a .json sidecar, but this is a non-standard format that
    WILL NOT WORK in a non-CART context!

    TODO: Implement the aforementioned side-car implementation

    :param path: Path to the NiFTI file to load
    :param reference_volume: Volume node to use as reference for IJK co-ordinates.
        If none, the markups will be placed using their native IJK values
    """
    # We guard everything with a try-catch to ensure the scene is cleaned
    # up properly if an error occurs during runtime.
    volume_rep_node = None
    markup_node = None
    try:
        # Load the NiFTI file initially as a volume
        volume_rep_node = load_volume(path)

        # Get the voxel array from the node
        volume_array = slicer.util.arrayFromVolume(volume_rep_node)

        # Get the set of indices for non-zero values in the "volume"
        nonzero_map = np.nonzero(volume_array)

        # It is exceedingly unlikely that a NiFTI-style markup has more than
        # 100 markups in it; if this is the case, warn the user!
        if nonzero_map[0].shape[0] > 100:
            print(
                f"WARNING: The number of markups in the NiFTI file '{path}' "
                "is abnormally large (more than 100), and will likely cause lag.\n"
                "Are you sure this is a markup-style NiFTI file?"
            )

        # Generate an empty markup node
        markup_node = slicer.mrmlScene.AddNewNodeByClass(
            'vtkMRMLMarkupsFiducialNode',
            'new_cart_nifti_markup'
        )

        # Generate our IJK -> RAS transformation function
        ijk_to_ras_transform = vtk.vtkMatrix4x4()
        volume_rep_node.GetIJKToRASMatrix(ijk_to_ras_transform)
        def _ijk_to_ras(ijk_pos):
            # Extend the IJK position to 4 dimensions to allow quaternion transforms
            ijk_pos_4d = np.array([
                # KO: No clue why the IJK needs to be flipped here...
                ijk_pos[2], ijk_pos[1], ijk_pos[0], 1
            ])

            # Apply the quaternion IJK -> RAS transform
            vol_pos_4d = [0, 0, 0, 1]
            ijk_to_ras_transform.MultiplyPoint(ijk_pos_4d, vol_pos_4d)

            # Trim the 4th value, as it isn't relevant
            vol_pos = np.array(vol_pos_4d[0:3])

            # Apply any (implicit) transforms the reference volume may have as well
            volume_to_ras_transform = vtk.vtkGeneralTransform()
            slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(
                volume_rep_node.GetParentTransformNode(),
                None,
                volume_to_ras_transform
            )
            ras_pos = volume_to_ras_transform.TransformPoint(vol_pos)

            # Return the result
            return ras_pos

        # Load the label map from a JSON sidecar, if it exists
        sidecar_data = load_json_sidecar(path)
        label_map = None
        if sidecar_data is not None:
            label_map = {
                int(k): v for k, v
                in sidecar_data.get(NIFTI_SIDECAR_LABELS_KEY, {}).items()
            }

        # For each position in the nonzero map, add a new markup label
        for ijk_pos in np.transpose(nonzero_map):
            # Get the value at this point; it will determine our label
            val = volume_array[ijk_pos[0], ijk_pos[1], ijk_pos[2]]

            # Calculate the Voxel position into RAS co-ordinates
            ras_pos = _ijk_to_ras(ijk_pos)

            # Determine the label for this markup
            label = str(val)
            if label_map is not None:
                label = label_map.get(val, label)

            # Add a new markup label at this position
            markup_node.AddControlPointWorld(
                (ras_pos[0], ras_pos[1], ras_pos[2]),
                label
            )
    except Exception as e:
        # If an error occurs, delete the markup node from the scene (if it exists)
        if markup_node:
            slicer.mrmlScene.RemoveNode(markup_node)
        # THEN raise the error
        raise e
    finally:
        # No matter what happens, try to delete the volume node as well
        if volume_rep_node:
            slicer.mrmlScene.RemoveNode(volume_rep_node)

    # Return the resulting markup node
    return markup_node


## SAVING ##
def save_volume_to_nifti(volume_node, path: Path):
    """
    Save a volume node to the specified path.
    """
    # Confirm this is a NiFTI file
    if ".nii" not in path.suffixes:
        raise ValueError(
            f"Refusing to save file '{path.name}' into NiFTI format; "
            "ensure the file is a '.nii' file!"
        )

    slicer.util.saveNode(volume_node, str(path))


def save_segmentation_to_nifti(segment_node, volume_node, path: Path):
    """
    Save a segmentation node's contents to a `.nii` file.

    Much like loading, we can't save segmentations directly. Instead, we need to
    convert it back to a label-type node w/ reference to a volume node first,
    then save that.
    """
    # Confirm this is a NiFTI file
    if ".nii" not in path.suffixes:
        raise ValueError(
            f"Refusing to save file '{path.name}' into NiFTI format; "
            "ensure the file is a '.nii' file!"
        )

    # Convert the Segmentation back to a Label (for Nifti export)
    label_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
    slicer.modules.segmentations.logic().ExportVisibleSegmentsToLabelmapNode(
        segment_node, label_node, volume_node
    )

    # Save the active segmentation node to the desired directory
    slicer.util.saveNode(label_node, str(path))

    # Clean up the label node after so it doesn't pollute the scene
    slicer.mrmlScene.RemoveNode(label_node)


def save_markups_to_json(markups_node, path: Path):
    """
    Save a markups node to the specified path as a JSON file.
    """
    # Confirm this is a correct file type
    if not path.name.endswith(".mrk.json"):
        raise ValueError(f"Refusing to save file '{path.name}' into Slicer MRK format.")
    # Use Slicer's utility function to save the markups node
    slicer.util.saveNode(markups_node, str(path))


def save_markups_to_nifti(
        markup_node: "vtk.vtkMRMLMarkupsFiducialNode",
        reference_volume: "vtk.vtkMRMLScalarVolumeNode",
        path: Path,
        master_profile: Optional[MasterProfileConfig] = None):
    """
    Saves a set of markup labels to a NiFTI file.

    This format is BIDS compliant, but has several caveats to its use:
        * Markups stored in NiFTI cannot support overlapping markup positions!
        * NiFTI cannot natively save the label names for each value within it
        * NiFTI can only save co-ordinates at IJK integer precision,
            unlike Slicer's JSON format (which tracks floating point RAS positions)
        * Requires a reference volume to convert the markups RAS co-ordinates to
            IJK voxel positions

    We work around some of these limitations via a `.json` sidecar, but this is a
    non-standard format that WILL NOT BE RECOGNIZED in non-CART contexts!

    :param markup_node: The markup node whose contents should be saved
    :param reference_volume: A reference volume, for converting RAS -> IJK co-ordinates
    :param path: Path to a (presumably `.nii`) file where the data should be saved
    :param master_profile: Profile config; used to build the JSON sidecar
    """
    # Confirm this is a NiFTI file
    if ".nii" not in path.suffixes:
        raise ValueError(
            f"Refusing to save file '{path.name}' into NiFTI format; "
            "ensure the file is a '.nii' file!"
        )

    # Build the RAS (world) -> IJK (voxel) transform function
    ras_to_kji_transform = vtk.vtkMatrix4x4()
    reference_volume.GetRASToIJKMatrix(ras_to_kji_transform)

    def _ras_to_ijk(ras_pos):
        # Convert the RAS position to volume position
        ras_to_volume_transform = vtk.vtkGeneralTransform()
        slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(
            None,
            reference_volume.GetParentTransformNode(),
            ras_to_volume_transform
        )
        vol_pos = ras_to_volume_transform.TransformPoint(ras_pos)

        # Extend the RAS position to 4 dimensions to allow quaternion transforms
        vol_pos_4d = np.append(vol_pos, 1)

        # Apply the quaternion RAS -> KJI transform
        # KO: I don't know why it's not IJK by default; it just is
        kji_pos_4d = [0, 0, 0, 1]
        ras_to_kji_transform.MultiplyPoint(vol_pos_4d, kji_pos_4d)

        # Trim the 4th value, as it isn't relevant
        kji_pos = np.array([int(round(v)) for v in kji_pos_4d[0:3]])

        # Flip the values from KJI into IJK
        ijk_pos = np.array([
            kji_pos[2], kji_pos[1], kji_pos[0]
        ])
        return ijk_pos

    # Group markup points of identical labels, and track their (voxel) positions
    label_map = dict()
    for i in range(markup_node.GetNumberOfControlPoints()):
        # Pull the markups position and label
        markup_label = markup_node.GetNthControlPointLabel(i)
        markup_pos = markup_node.GetNthControlPointPositionWorld(i)
        # Track it in the map
        map_entry = label_map.get(markup_label, None)
        if map_entry is None:
            # If no entry for this label exists yet, assign one
            map_entry = []
            label_map[markup_label] = map_entry
        # Convert the markup's RAS position to IJK voxel position
        markup_ijk_pos = _ras_to_ijk(markup_pos)
        # Track the result
        map_entry.append(markup_ijk_pos)

    markup_segment_node = None
    try:
        # Initialize the JSON sidecar's contents
        sidecar_data = {}
        creation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # If we have a user profile, add its contents to the GeneratedBy entry
        if master_profile:
            sidecar_data["GeneratedBy"] = [{
                "Name": "CART",
                "Author": master_profile.author,
                "Position": master_profile.position,
                "Date": creation_time
            }]
        # Otherwise, just note that this was created by CART
        else:
            sidecar_data["GeneratedBy"] = [{
                "Name": "CART",
                "Date": creation_time
            }]

        # Add a map (dict) to track the label value -> label names in the sidecar
        sidecar_labelmap = dict()
        sidecar_data[NIFTI_SIDECAR_LABELS_KEY] = sidecar_labelmap

        # Initiate a segmentation node to place the markup labels into
        markup_segment_node = create_empty_segmentation_node(
            name="CART_OUTPUT_TMP",
            reference_volume=reference_volume
        )

        # Place segments into it, one per label
        for idx, (label, pos_list) in enumerate(label_map.items()):
            # Build the blank segment
            segment_id = markup_segment_node.GetSegmentation().AddEmptySegment("", label)
            segment_array = slicer.util.arrayFromSegmentBinaryLabelmap(
                markup_segment_node,
                segment_id,
                reference_volume
            )
            # Mark the corresponding positions in the segment
            for (i, j, k) in pos_list:
                segment_array[i, j, k] = 1
            # Update the segmentation using the updated segment array
            slicer.util.updateSegmentBinaryLabelmapFromArray(
                segment_array,
                markup_segment_node,
                segment_id,
                reference_volume
            )
            # Add the corresponding label to the sidecar's label map
            sidecar_labelmap[int(idx+1)] = label

        # Save the segmentation to the designated path
        save_segmentation_to_nifti(markup_segment_node, reference_volume, path)

        # Save the sidecar alongside it
        save_json_sidecar(path, sidecar_data)
    finally:
        # Ensure that, no matter what, the segmentation node is removed
        if markup_segment_node:
            slicer.mrmlScene.RemoveNode(markup_segment_node)


## SIDECAR FILES ##
def find_json_sidecar_path(main_file_path: Path) -> Path:
    """
    Generate a path to where the JSON sidecar for a given file would be.

    Note that YOU are responsible for checking whether the file exists
    or not, and handling the result appropriately.
    """
    # Identify where the JSON sidecar should be
    sidecar_fname = main_file_path.name.split(main_file_path.suffixes[0])[0] + ".json"
    sidecar_path = main_file_path.parent / sidecar_fname

    # Return the result
    return sidecar_path


def load_json_sidecar(main_file_path: Path) -> Optional[dict]:
    """
    Tries to load the contents of a JSON sidecar associated with
    the passed file.

    Returns None if the file does not exist, or was a directory.
    """
    # Get the path to where the sidecar should be
    sidecar_path = find_json_sidecar_path(main_file_path)

    # If it doesn't exist, return None
    if not sidecar_path.exists() or not sidecar_path.is_file():
        return None

    # Otherwise, try to load the contents of the file and return it
    with open(sidecar_path, "r") as fp:
        sidecar_data = json.load(fp)
        return sidecar_data


def save_json_sidecar(main_file_path: Path, sidecar_data: dict):
    """
    Tries to save the sidecar data into a JSON sidecar, sharing the same
    file name and directory as the main file
    """
    # Get the path to where the sidecar should be
    sidecar_path = find_json_sidecar_path(main_file_path)

    # Otherwise, try to load the contents of the file and return it
    with open(sidecar_path, 'w') as fp:
        json.dump(sidecar_data, fp, indent=2)


GENERATED_BY_KEY = "GeneratedBy"


# noinspection PyUnusedLocal
@singledispatch
def add_generated_by_entry(
        sidecar_data: Any,
        profile: Optional[MasterProfileConfig] = None
):
    """
    Adds a new "GeneratedBy" entry to the specified sidecar, IN-PLACE!

    If `json_context` is a Path, will insert into the specified file,
    creating it if one does not already exist.

    If `json_context` is a dictionary, will extend the current "GeneratedBy"
    entry with the new entry, creating such a list if it does not already
    exist.

    :param sidecar_data: The sidecar to insert into, in either Path or dictionary form.
    :param profile: The profile whose username + role to reference. If not provided, the
        'Author' and 'Role' fields will be omitted from the new entry.
    """
    raise NotImplemented(
        f"Writing a '{GENERATED_BY_KEY}' entry to an object "
        f"of type '{type(sidecar_data)}' is not yet supported!"
    )


@add_generated_by_entry.register
def _add_gb_entry_to_file(
        json_file: Path,
        profile: Optional[MasterProfileConfig] = None
):
    """
    Adds a new "GeneratedBy" entry to the specified sidecar path, IN-PLACE!

    If the specified sidecar file does not already exist, will create
    one w/ the new entry instead.
    """
    # Load the sidecar's contents, if the already exist
    if json_file.exists():
        # If the sidecar isn't a file, raise an error
        if json_file.is_file():
            raise ValueError(f"Cannot save '{GENERATED_BY_KEY}' entry to '{str(json_file.resolve())}'; "
                             f"destination is not a valid file!")
        with open(json_file, "r") as fp:
            json_data = json.load(fp)
    else:
        json_data = dict()

    # Update the contents of the resulting dictionary w/ the specified file.
    _add_gb_entry_to_dict(json_data, profile)

    # Save the result back to the file
    with open(json_file, "w") as fp:
        json.dump(json_data, fp)


@add_generated_by_entry.register
def _add_gb_entry_to_dict(
        json_data: dict,
        profile: Optional[MasterProfileConfig]
):
    """
    Adds a new "GeneratedBy" entry to the specified sidecar path.

    If a "GeneratedBy" entry doesn't already exist within the provided
    dictionary, appends to it instead.
    """
    # Update the dictionary with a new "GeneratedBy" entry inplace
    generated_by_entries = json_data.get(GENERATED_BY_KEY, [])
    creation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if profile:
        generated_by_entries.append(
            {
                "Name": "CART",
                "Author": profile.author,
                "Position": profile.position,
                "Date": creation_time,
            }
        )
    else:
        generated_by_entries.append(
            {
                "Name": "CART",
                "Date": creation_time,
            }
        )
    json_data[GENERATED_BY_KEY] = generated_by_entries


def stack_sidecars(*sidecar_paths: Path) -> dict:
    """
    Stack the contents of a list of sidecar paths into a single dictionary.

    Does **NOT** save the dictionaries contents; it's your responsibility to
    save (after doing any other changes you'd like) the contents to a file.

    See Also
    --------
    save_json_sidecar : Save the resulting dictionary to a sidecar associated with a given file.
    stack_json_dicts : Function for stacking dictionaries, used by this function.
    """
    final_data = dict()
    for p in sidecar_paths:
        if not p.exists():
            print(f"Skipped file '{str(p.resolve())}', as it does not exist!")
            continue
        elif not p.is_file():
            print(f"Skipped file '{str(p.resolve())}', as it was not a valid file!")
            continue
        with open(p, 'r') as fp:
            p_data = json.load(fp)
        stack_json_dicts(source = p_data, dest = final_data)
    return final_data


def stack_json_dicts(source: dict, dest: dict):
    """
    Stacks two dictionaries, copying the contents of 'source' into 'dest'.

    If a given key within the destination dictionary also exists within the source dictionary,
    the value within the destination is overwritten by the source's values.
    There are **two** exceptions to this behavior:

    * If the values in both are lists, they will be concatenated
    * If the values in both are dicts, they are stacked recursively.

    :param source: The dictionary whose contents should be copied *from*
    :param dest: The dictionary whose contents should be copied *to*
    :returns: The ``dest`` dictionary, now modified by the contents of ``source``

    Example
    -------
    >>> source_dict = {
    >>>     "id": 1
    >>>     "math_vars": ["x", "y", "z"]
    >>>     "label_map": {
    >>>         "foo": "bar",
    >>>         "bingo": "bravo"
    >>>     }
    >>> }
    >>> dest_dict = {
    >>>     "id": 2
    >>>     "math_vars": ["a", "b", "c"]
    >>>     "label_map": {
    >>>         "bingo": "british",
    >>>         "charlie": "chaplin"
    >>>     }
    >>> }
    >>> stack_json_dicts(source_dict, dest_dict)
    >>> dest_dict
    {
         "id": 2
         "math_vars": ["a", "b", "c", "x", "y", "z"]
         "label_map": {
             "foo": "bar",
             "bingo": "british",
             "charlie": "chaplin"
         }
    }

    """
    # Iterate all entries in the "source" JSON dictionary
    for k, v in source.items():
        # For lists, try to extend them
        if type(v) is list:
            dv = dest.get(k, [])
            # If the destination value isn't already a list, overwrite it
            if type(dv) is not list:
                dest[k] = v
            else:
                dest[k] = [*v, *dv]
        # For dicts, act recursively
        if type(v) is dict:
            dv = dest.get(k, {})
            # If the destination value was not already a dict, overwrite it
            if type(dv) is not dict:
                dest[k] = v
            # Otherwise, stack the dicts recursively
            else:
                stack_json_dicts(v, dv)
                dest[k] = dv
        # For all others, insert/overwrite
        else:
            dest[k] = v

## ORGANIZATION ##
def create_subject(label: str, *child_nodes):
    # Get Slicer's hierarchy node
    shNode = slicer.mrmlScene.GetSubjectHierarchyNode()

    # Create a new subject with the desired label
    subject_id = shNode.CreateSubjectItem(shNode.GetSceneItemID(), label)

    # Have the new subject "adopt" all provided child nodes
    for n in child_nodes:
        n_id = shNode.GetItemByDataNode(n)
        shNode.SetItemParent(n_id, subject_id)

    # Return the ID for the newly created subject
    return subject_id


def extract_case_keys_by_prefix(
    case_data: dict[str, str], prefix: str, force_present: bool = False
) -> list[str]:
    """
    Extract keys from a case_data dictionary where the given prefix
    appears as a full word (split by "_"), case-insensitively.

    Parameters
    ----------
    case_data : dict[str, str]
        Dictionary containing keys like 'T2w_Volume', 'Lesion_Segmentation', etc.
    prefix : str
        The prefix to match exactly (e.g., "Volume", "Segmentation", "Markup").
    force_present: bool
        Whether to raise an error if no keys match the prefix.

    Returns
    -------
    list[str]
        Keys in case_data that contain the prefix as a full word.

    """
    prefix_lower = prefix.lower()
    keys = [
        k for k in case_data if prefix_lower in (part.lower() for part in k.split("_"))
    ]
    if not keys and force_present:
        raise ValueError(
            f"No keys found with prefix '{prefix}' in case_data: {case_data}"
        )
    return keys


def create_empty_segmentation_node(
    name: str,
    reference_volume: slicer.vtkMRMLScalarVolumeNode,
    scene: Optional[slicer.vtkMRMLScene] = None,
) -> slicer.vtkMRMLSegmentationNode:
    """
    Create an empty segmentation node with proper display node setup.

    # TODO CREATE SUPPORT FOR KWARGS TO PASS TO THE DISPLAY NODE

    Args:
        name: Name for the segmentation node
        reference_volume: Volume node to use for geometry reference
        scene: MRML scene to add the node to (defaults to slicer.mrmlScene)

    Returns:
        Empty segmentation node with display node configured
    """
    if scene is None:
        scene = slicer.mrmlScene

    # Create segmentation node
    seg_node = slicer.vtkMRMLSegmentationNode()
    scene.AddNode(seg_node)
    seg_node.SetName(name)

    # Create and set up display node
    display_node = slicer.vtkMRMLSegmentationDisplayNode()
    scene.AddNode(display_node)
    seg_node.SetAndObserveDisplayNodeID(display_node.GetID())

    # Set reference geometry
    seg_node.SetReferenceImageGeometryParameterFromVolumeNode(reference_volume)

    return seg_node


## COHORT STRATIFICATION ##
# TODO: Move these 'parse' functions into CARTStandardUnit
#  to prevent accidental mis-use
VOLUME_PREFIX = 'Volume'
SEGMENTATION_PREFIX = 'Segmentation'
MARKUP_PREFIX = 'Markup'

def parse_volumes(
    case_data: dict[str, Any], data_path: Path
) -> tuple[list[str], dict[str, Path], str]:
    # Get the keys from the case data
    volume_keys = extract_case_keys_by_prefix(case_data, VOLUME_PREFIX, force_present=True)

    # We need at least one volume key; otherwise theirs nothing to reference against
    if len(volume_keys) < 1:
        raise ValueError("At least one feature in the cohort must be a volume!")

    # Parse the volume paths

    volume_paths: dict[str, Optional[Path]] = {
        (k): (data_path / v if (v := case_data.get(k, "")) != "" else None)
        for k in volume_keys
    }

    # We need at least one non-blank path to reference against
    valid_paths: dict[str, Path] = {
        k: v for k, v in volume_paths.items() if v is not None
    }
    if len(valid_paths) < 1:
        raise ValueError(
            f"No valid volumes were found for case '{case_data.get('uid', 'UNKNOWN')}'!"
        )

    # Set the primary volume to reference segmentations against
    # KO: Note that this will select a non-primary volume if all primary volumes are
    #  blank; not the most intuitive, but much better than just crashing
    primary_volume_key = next(
        # Prefer a key explicitly designated as "primary" if possible
        (k for k in valid_paths.keys() if "primary" in k.lower()),
        # Failing that, select the first valid volume instead
        next(iter(valid_paths.keys())),
    )

    # Move the primary key to the front of our list
    volume_keys.remove(primary_volume_key)
    volume_keys = [primary_volume_key, *volume_keys]
    return volume_keys, volume_paths, primary_volume_key


# TODO: Remove the "default fallback"
def parse_segmentations(
    case_data, data_path
) -> tuple[list[str], dict[str, Path]]:
    # Parse our segmentation keys
    segmentation_keys = extract_case_keys_by_prefix(
        case_data, SEGMENTATION_PREFIX, force_present=False
    )

    # If there were none, end here
    if not segmentation_keys:
        return [], {}

    # Initialize our segmentation paths
    segmentation_paths: dict[str, Path] = {
        (k): (data_path / v if (v := case_data.get(k, "")) != "" else None)
        for k in segmentation_keys
    }
    valid_segmentation_paths = {
        k: v for k, v in segmentation_paths.items() if v is not None
    }
    return segmentation_keys, valid_segmentation_paths


def parse_markups(case_data, data_path) -> tuple[list[str], dict[str, Path]]:
    # TODO Handle Case for allowing a "Primary" Markup even if we dont currently have a need.
    # This would allow us to dry out this code combining all 3 parse_* functions

    # Get our list of
    markup_keys = extract_case_keys_by_prefix(case_data, MARKUP_PREFIX, force_present=False)

    # Initialize our markup paths
    markup_paths: dict[str, Path] = {
        (k): (data_path / v if (v := case_data.get(k, "")) != "" else None)
        for k in markup_keys
    }
    valid_markup_paths = {k: v for k, v in markup_paths.items() if v is not None}
    return markup_keys, valid_markup_paths


## "Standard" Data Unit ##
class CARTStandardUnit(DataUnitBase):
    """
    A DataUnit instance which imports volumes, segmentations, and markup files
    in a standardized way. Also provides some convenience functionality, such as
    managing the currently viewed orientation(s) of the data unit's contents
    within Slicer's graphical viewer.
    """

    COMPLETED_KEY = "completed"

    DEFAULT_ORIENTATION = Orientation.AXIAL

    FEATURE_CLASSES = {
        VOLUME_PREFIX:
            "An anatomical volume you want to view. "
            "Must have 'volume' in its name.",
        SEGMENTATION_PREFIX:
            "A segmentation label to overlay on viewed volumes. "
            "Must have 'segmentation' in its name.",
        MARKUP_PREFIX:
            "A set of named point markups to indicate on viewed volumes. "
            "Must have 'markup' in its name."
    }

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ) -> None:
        super().__init__(case_data, data_path, scene)

        # The primary volume acts as the "reference" co-ordinate system + orientation
        # for all other volumes, segmentation, and markups
        self.volume_keys: list[str]
        self.volume_paths: dict[str, Path]
        self.primary_volume_key: str
        self.volume_keys, self.volume_paths, self.primary_volume_key = parse_volumes(
            case_data, data_path
        )
        self.volume_nodes: dict[str, slicer.vtkMRMLScalarVolumeNode] = dict()

        # Segmentation-related parameters
        self.segmentation_keys: list[str]
        self.segmentation_paths: dict[str, Path]
        self.segmentation_keys, self.segmentation_paths = parse_segmentations(case_data, data_path)
        self.segmentation_nodes: dict[str, slicer.vtkMRMLSegmentationNode] = dict()

        # Markup-related parameters
        self.markup_keys: list[str]
        self.markup_paths: dict[str, Path]
        self.markup_keys, self.markup_paths = parse_markups(case_data, data_path)
        self.markup_nodes: dict[str, slicer.vtkMRMLMarkupsFiducialNode] = dict()

        # Load everything into memory
        self._initialize_resources()

        # Create a subject associated with this data unit
        self.hierarchy_node = scene.GetSubjectHierarchyNode()
        self.subject_id = create_subject(
            self.uid,
            *self.segmentation_nodes.values(),
            *self.volume_nodes.values(),
            *self.markup_nodes.values(),
        )

        self.is_complete = case_data.get(self.COMPLETED_KEY, False)

    def to_dict(self) -> dict[str, str]:
        """Serialize back to case_data format."""
        output = {key: self.case_data[key] for key in self.volume_keys}
        output.update({key: self.case_data[key] for key in self.segmentation_keys})
        output.update({key: self.case_data[key] for key in self.markup_keys})
        output[self.COMPLETED_KEY] = self.is_complete
        return output

    @property
    def layout_handler(self) -> LayoutHandler:
        # If we don't have a layout handler yet, generate one
        if not self._layout_handler:
            self._layout_handler = LayoutHandler(
                volume_nodes=list(self.volume_nodes.values()),
                primary_volume_node=self.primary_volume_node,
                orientation=self.DEFAULT_ORIENTATION,
            )
        return self._layout_handler

    def focus_gained(self) -> None:
        """Show all volumes and segmentation when this unit gains focus."""
        # Call the super function
        super().focus_gained()

        # Reveal all the data nodes again
        for node in itertools.chain(
            self.volume_nodes.values(),
            self.segmentation_nodes.values(),
            self.markup_nodes.values(),
        ):
            node.SetDisplayVisibility(True)
            node.SetSelectable(True)
            node.SetHideFromEditors(False)

        self._set_subject_shown(True)

    def focus_lost(self) -> None:
        """Hide all volumes and segmentation when focus is lost."""
        # Call the super function
        super().focus_lost()

        # Hide all data nodes again
        for node in itertools.chain(
            self.volume_nodes.values(),
            self.segmentation_nodes.values(),
            self.markup_nodes.values(),
        ):
            node.SetDisplayVisibility(False)
            node.SetSelectable(False)
            node.SetHideFromEditors(True)

        self._set_subject_shown(False)

    def clean(self) -> None:
        """Clean up the hierarchy node and its children."""
        super().clean()

        # If we are bound to a subject, remove it from the scene
        if self.subject_id is not None:
            self.hierarchy_node.RemoveItem(self.subject_id)

    def validate(self) -> None:
        """
        Ensure that all discovered volume keys and the segmentation key
        refer to existing files.
        """
        for key in self.volume_keys:
            self.validate_key_is_file(key)
        for key in self.segmentation_keys:
            if key is not None:
                self.validate_key_is_file(key)

    def validate_key_is_file(self, key: str) -> None:
        """
        Confirm that `case_data[key]` exists, is a path under data_path,
        and refers to a file.
        """
        rel_path = self.case_data.get(key)
        # If the path wasn't specified, we assume the user wants it skipped/created
        if not rel_path:
            return
        # If there was a path, ensure it exists and is a file
        full_path = self.data_path / rel_path
        if not full_path.exists():
            raise ValueError(f"Path for '{key}' does not exist: {full_path}")
        if not full_path.is_file():
            raise ValueError(f"Path for '{key}' is not a file: {full_path}")

    def _initialize_resources(self) -> None:
        """
        Load volume nodes and segmentation nodes, align geometry,
        and register under a single subject in the hierarchy.
        """
        self._init_volume_nodes()
        self._init_segmentation_nodes()
        self._init_markups_nodes()

    def _init_volume_nodes(self) -> None:
        """
        Load each volume path into a volume node, name it,
        store in resources, and identify the primary.
        """
        for key, path in self.volume_paths.items():
            # If the volume is blank, skip it
            if path is None:
                continue
            # Attempt to load the volume and track it
            node = load_volume(path)
            node.SetName(f"{key} ({self.uid})")
            self.volume_nodes[key] = node
            self.resources[key] = node

            # If this is our primary volume, track it outright for ease of reference
            if key == self.primary_volume_key:
                self.primary_volume_node = node

    def _init_segmentation_nodes(self) -> None:
        """
        For each segmentation key, load if file exists.
        """
        # If we don't have a primary volume yet, this method was called too early
        if not self.primary_volume_node:
            raise ValueError(
                "Cannot initialize segmentation nodes prior to volume nodes!"
            )

        # Prepare to set the color of each segment
        color_table = slicer.util.getNode("GenericColors").GetLookupTable()
        c_idx = 2  # Start at 2, so newly created segments can have a unique color
        for key in self.segmentation_keys:
            seg_path = self.segmentation_paths.get(key, None)
            if seg_path and seg_path.exists():
                # Try to load the segmentation first
                node = load_segmentation(seg_path)
            else:
                # If that fails, skip over it
                continue

            # Set the name of the node, and align it to our primary volume
            node.SetName(f"{key} ({self.uid})")
            node.SetReferenceImageGeometryParameterFromVolumeNode(
                self.primary_volume_node
            )

            # Apply a unique color to all segments within the segmentation
            for segment_id in node.GetSegmentation().GetSegmentIDs():
                print(f"Setting color for segment '{segment_id}' in '{key}'.")
                segment = node.GetSegmentation().GetSegment(segment_id)

                # TODO MAKE THIS COLOR SETTING A UTIL FUNCTION AND MORE CONFIGURABLE
                # Get the corresponding color, w/ Alpha stripped from it
                segmentation_color = color_table.GetTableValue(c_idx)[:-1]
                segment.SetColor(*segmentation_color)

                # Increment the color index
                c_idx += 1
            self.segmentation_nodes[key] = node
            self.resources[key] = node

    def _init_markups_nodes(self) -> None:
        """
        Load each markup path into a markups node, name it,
        store in resources, and identify the primary.
        """
        for key, path in self.markup_paths.items():
            # If the markup was blank, skip it
            if path is None:
                continue
            # Try to load all markups from the file
            nodes = load_markups(path)
            should_iter = len(nodes) > 1
            for i, node in enumerate(nodes):
                # Error out if the node is of the wrong type
                if not isinstance(node, slicer.vtkMRMLMarkupsFiducialNode):
                    raise TypeError(
                        f"Expected a MarkupsFiducialNode, got {type(node)} for key {key}"
                    )
                # Determine how the node should be keyed
                if should_iter:
                    name = f"{key} ({self.uid}) [{i}]"
                else:
                    name = f"{key} ({self.uid})"
                # Update the node's properties and track it
                node.SetName(name)
                self.markup_nodes[name] = node
                self.resources[name] = node

    def _set_subject_shown(self, new_state: bool) -> None:
        """
        Expand or collapse the subject hierarchy group.
        """
        if self.subject_id is not None:
            self.hierarchy_node.SetItemExpanded(self.subject_id, new_state)
            self.hierarchy_node.SetItemDisplayVisibility(self.subject_id, new_state)

    ## Utilities ##
    @classmethod
    def feature_types(cls) -> dict[str, str]:
        """
        Report our own valid feature types for Tasks which use this class
        as a data unit factory
        """
        return cls.FEATURE_CLASSES

    @classmethod
    def feature_label_for(cls, init_label: str, feature_type: str):
        # Always skip over the "None" feature type
        if feature_type.lower() == "none":
            return init_label
        # Check all prefixes one-at-a-time
        # TODO; convert this to a switch statement
        for prefix in [VOLUME_PREFIX, SEGMENTATION_PREFIX, MARKUP_PREFIX]:
            # If the feature type doesn't match, skip
            if feature_type != prefix:
                continue
            # If the prefix is already in the label, return untouched
            if prefix in init_label:
                return init_label
            # Otherwise, add the prefix to the label and return
            return f"{prefix}_{init_label}"
        # If the feature type doesn't match any known type, return unchanged w/ a warning
        print(f"Unknown feature type '{feature_type}' for a data unit of type '{cls.__name__}'")
        return init_label
