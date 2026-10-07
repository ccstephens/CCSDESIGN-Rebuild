from __future__ import annotations

import numpy as np
import trimesh

AXES = {"x": 0, "y": 1, "z": 2}


def _mirror_transform(axis_index: int, plane: float) -> np.ndarray:
    transform = np.eye(4)
    transform[axis_index, axis_index] = -1.0
    transform[axis_index, 3] = 2.0 * plane
    return transform


def create_mirrored_repair(mesh: trimesh.Trimesh, axis: str, keep_side: str, overlap_mm: float = 0.4) -> tuple[trimesh.Trimesh, trimesh.Trimesh, float]:
    if axis not in AXES:
        raise ValueError("axis must be x, y or z")
    if keep_side not in {"positive", "negative"}:
        raise ValueError("keep_side must be positive or negative")
    if overlap_mm < 0 or overlap_mm > 5:
        raise ValueError("overlap_mm must be between 0 and 5 mm")
    idx = AXES[axis]
    plane = float(mesh.bounding_box.centroid[idx])
    centers = mesh.triangles_center[:, idx]
    mask = centers >= plane - overlap_mm if keep_side == "positive" else centers <= plane + overlap_mm
    if not np.any(mask):
        raise ValueError("No faces were found on the selected intact side")
    intact = mesh.submesh([np.nonzero(mask)[0]], append=True, repair=False)
    if not isinstance(intact, trimesh.Trimesh) or len(intact.faces) == 0:
        raise ValueError("Could not isolate the selected intact geometry")
    patch = intact.copy()
    patch.apply_transform(_mirror_transform(idx, plane))
    patch.invert()
    combined = trimesh.util.concatenate((mesh.copy(), patch.copy()))
    combined.merge_vertices();combined.remove_unreferenced_vertices();trimesh.repair.fix_normals(combined, multibody=True)
    return patch, combined, plane


def create_selected_mirrored_repair(mesh: trimesh.Trimesh, axis: str, point: list[float], radius_mm: float, overlap_mm: float = 0.4) -> tuple[trimesh.Trimesh, trimesh.Trimesh, float, int, int, int, int]:
    """Replace a selected damaged region with mirrored geometry from the intact opposite side."""
    if axis not in AXES:
        raise ValueError("axis must be x, y or z")
    if len(point) != 3 or not np.all(np.isfinite(point)):
        raise ValueError("A valid 3D damaged-area point is required")
    if radius_mm <= 0:
        raise ValueError("Selection radius must be greater than zero")
    if overlap_mm < 0 or overlap_mm > 5:
        raise ValueError("overlap_mm must be between 0 and 5 mm")

    idx = AXES[axis]
    plane = float(mesh.bounding_box.centroid[idx])
    target = np.asarray(point, dtype=float)
    donor = target.copy()
    donor[idx] = 2.0 * plane - target[idx]
    centers = np.asarray(mesh.triangles_center)

    target_distance = np.linalg.norm(centers - target, axis=1)
    donor_distance = np.linalg.norm(centers - donor, axis=1)
    # Remove a slightly larger target region when overlap is requested. This creates a
    # controlled replacement zone instead of leaving the mirrored patch stacked over old faces.
    target_mask = target_distance <= radius_mm + overlap_mm
    donor_mask = donor_distance <= radius_mm + overlap_mm
    removed_count = int(np.count_nonzero(target_mask))
    donor_count = int(np.count_nonzero(donor_mask))

    if donor_count == 0:
        raise ValueError("No intact donor geometry was found opposite the selected damaged area. Increase the selection radius or choose another symmetry axis.")
    if removed_count == len(mesh.faces):
        raise ValueError("The selected radius covers the entire model. Reduce the selection radius.")

    donor_mesh = mesh.submesh([np.nonzero(donor_mask)[0]], append=True, repair=False)
    if not isinstance(donor_mesh, trimesh.Trimesh) or len(donor_mesh.faces) == 0:
        raise ValueError("Could not isolate donor geometry for this selection")

    patch = donor_mesh.copy()
    patch.apply_transform(_mirror_transform(idx, plane))
    patch.invert()

    keep_mask = ~target_mask
    if np.any(keep_mask):
        base = mesh.submesh([np.nonzero(keep_mask)[0]], append=True, repair=False)
        combined = trimesh.util.concatenate((base, patch.copy()))
    else:
        combined = patch.copy()

    combined.merge_vertices(merge_tex=True, merge_norm=True)
    combined.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(combined, multibody=True)
    # Report seam health immediately. Exact mirrored topology can weld perfectly; scanned or
    # asymmetric geometry may still leave boundary/non-manifold edges and must be reviewed.
    edge_counts = np.bincount(combined.edges_unique_inverse)
    boundary_edges = int(np.count_nonzero(edge_counts == 1))
    non_manifold_edges = int(np.count_nonzero(edge_counts > 2))
    return patch, combined, plane, donor_count, removed_count, boundary_edges, non_manifold_edges
