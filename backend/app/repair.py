from __future__ import annotations

import numpy as np
import trimesh

AXES = {"x": 0, "y": 1, "z": 2}


def create_mirrored_repair(mesh: trimesh.Trimesh, axis: str, keep_side: str, overlap_mm: float = 0.4) -> tuple[trimesh.Trimesh, trimesh.Trimesh, float]:
    """Create a first-pass repair by mirroring intact geometry across a user-selected symmetry plane.

    This V1 repair mode is deliberately non-destructive: it returns both the generated patch and a
    combined preview. The original source mesh is never overwritten.
    """
    if axis not in AXES:
        raise ValueError("axis must be x, y or z")
    if keep_side not in {"positive", "negative"}:
        raise ValueError("keep_side must be positive or negative")
    if overlap_mm < 0 or overlap_mm > 5:
        raise ValueError("overlap_mm must be between 0 and 5 mm")

    idx = AXES[axis]
    plane = float(mesh.bounding_box.centroid[idx])
    centers = mesh.triangles_center[:, idx]
    if keep_side == "positive":
        mask = centers >= plane - overlap_mm
    else:
        mask = centers <= plane + overlap_mm
    if not np.any(mask):
        raise ValueError("No faces were found on the selected intact side")

    intact = mesh.submesh([np.nonzero(mask)[0]], append=True, repair=False)
    if not isinstance(intact, trimesh.Trimesh) or len(intact.faces) == 0:
        raise ValueError("Could not isolate the selected intact geometry")

    transform = np.eye(4)
    transform[idx, idx] = -1.0
    transform[idx, 3] = 2.0 * plane
    patch = intact.copy()
    patch.apply_transform(transform)
    patch.invert()

    combined = trimesh.util.concatenate((mesh.copy(), patch.copy()))
    combined.merge_vertices()
    combined.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(combined, multibody=True)
    return patch, combined, plane
