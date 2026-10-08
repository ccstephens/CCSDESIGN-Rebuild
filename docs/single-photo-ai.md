# Local single-photo reconstruction (RTX 3080 10GB)

The backend now supports a separate **one-photo** path using an optional local TripoSR installation. Two or more photos continue through Meshroom. No hosted inference API is called.

## Installation on the Windows processing PC

1. Install a CUDA-capable NVIDIA driver and Python environment suitable for the upstream TripoSR project.
2. Clone the upstream [TripoSR project](https://github.com/VAST-AI-Research/TripoSR), review its licence and installation instructions, install its requirements and download model weights as required. GPU compatibility and exact dependency versions must be validated on your system.
3. In PowerShell, configure the two paths for the shell launching CCSDESIGN Rebuild:

```powershell
$env:CCSDESIGN_TRIPOSR_PYTHON = "C:\\AI\\TripoSR\\.venv\\Scripts\\python.exe"
$env:CCSDESIGN_TRIPOSR_SCRIPT = "C:\\AI\\TripoSR\\run.py"
.\\run-app.ps1
```

Replace the sample paths with the real ones. The app launches `python run.py <image> --output-dir <project-output> --device cuda:0` and collects the resulting OBJ/PLY/GLB/STL. TripoSR typically exports an OBJ mesh.

## Important limits

- One photo cannot reveal hidden geometry or guarantee physical dimensions.
- The current integration has not been tested on an RTX 3080 10GB. Out-of-memory errors may require smaller settings or different engine choices.
- The local AI engine is a **separate installation** at present; this is not yet a self-contained Windows installer.
- This is not text-to-3D, and image-based texture generation is not yet guaranteed.
- The current app has no public-network authentication. For iPhone access use **private Tailscale Serve**, not a public port forward or Tailscale Funnel.
- The server PC must remain on and accessible for iPhone-initiated generation.

## Verification checklist

1. Upload exactly one supported image to a project.
2. Start reconstruction; confirm it launches the configured Python executable.
3. Poll the reconstruction status and check `reconstruction.log` on errors.
4. Confirm the generated mesh appears in the project 3D viewer and can export as STL.
5. Repeat from Safari over the private tailnet HTTPS URL.

These are acceptance tests to perform, not claims that they have already passed.
