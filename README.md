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

V1 now includes persistent projects, 20–50 photo reconstruction with progress tracking, direct mesh import, interactive Three.js inspection, printability analysis, automatic mesh repair, selected-area mirrored missing-part reconstruction with seam validation, real-world scaling, STL export, dependency diagnostics and a single-server Windows launcher.


## Windows packaged build

The `Windows V1 Build` GitHub Actions workflow builds a self-contained CCSDESIGN Rebuild Windows folder using PyInstaller. The workflow now starts the generated executable on a Windows runner and requires `/api/health` and the projects API to respond before the build artifact is uploaded.

Projects created by the packaged application are stored persistently in `%LOCALAPPDATA%\CCSDESIGN Rebuild\projects`, outside the application bundle.

Download the `CCSDESIGN-Rebuild-Windows-V1` artifact from a successful Windows V1 Build workflow, extract the folder, and run `Start CCSDESIGN Rebuild.bat` or `CCSDESIGN-Rebuild.exe`.

Mesh import, analysis, repair, scaling and STL export are included in the packaged application. Photo reconstruction additionally requires Meshroom/AliceVision with `meshroom_batch` available on PATH.
