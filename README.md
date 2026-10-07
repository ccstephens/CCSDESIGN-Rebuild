# CCSDESIGN Rebuild

Windows-first application for turning photographs of complete or damaged real-world objects into repairable, correctly scaled 3D-print meshes and STL files.

## V1 workflow

1. Create a project.
2. Import 20–50 photographs of the object.
3. Reconstruct a 3D mesh with Meshroom/AliceVision.
4. Inspect mesh dimensions and printability indicators.
5. Set real-world scale from a known measurement.
6. Auto-repair common mesh defects.
7. Export a printable STL.

V1 also accepts an existing STL/OBJ/PLY/GLB/GLTF so the repair, scale and export pipeline can be tested before photogrammetry is installed.

## Stack

- React + TypeScript + Vite desktop-style frontend
- FastAPI Python backend
- Meshroom/AliceVision photogrammetry integration
- Trimesh mesh inspection, repair, scaling and STL export
- CadQuery is reserved for the engineering/missing-part generation stage

## Run on Windows

Requirements: Python 3.11, Node.js/npm and, for photo reconstruction, Meshroom/AliceVision with `meshroom_batch` available on PATH.

From PowerShell in the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run-dev.ps1
```

Then open `http://127.0.0.1:5173`. API documentation is at `http://127.0.0.1:8000/docs`.

## V1 status

The first V1 foundation includes project creation, multi-photo upload, Meshroom launch integration, direct mesh import, Trimesh analysis, automatic repair, measurement-based scaling, GLB preview generation and STL export. The next implementation step is the interactive Three.js mesh viewer followed by reconstruction job progress and stronger printability checks.
