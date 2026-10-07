from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Annotated

import trimesh
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

APP_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = APP_ROOT / "data"
PROJECT_ROOT = DATA_ROOT / "projects"
ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
ALLOWED_MESHES = {".obj", ".ply", ".stl", ".glb", ".gltf"}

PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="CCSDESIGN Rebuild API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectCreate(BaseModel):
    name: str


class ScaleRequest(BaseModel):
    current_mm: float
    target_mm: float


class ProjectInfo(BaseModel):
    id: str
    name: str
    image_count: int
    mesh_available: bool


def project_dir(project_id: str) -> Path:
    path = PROJECT_ROOT / project_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return path


def mesh_path(project_id: str) -> Path:
    meshes = project_dir(project_id) / "meshes"
    for name in ("scaled.stl", "repaired.stl", "reconstruction.obj", "reconstruction.ply", "source.stl", "source.obj", "source.ply"):
        candidate = meshes / name
        if candidate.exists():
            return candidate
    raise HTTPException(status_code=404, detail="No mesh is available for this project yet")


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise HTTPException(status_code=422, detail="Mesh contains no geometry")
        loaded = trimesh.util.concatenate(tuple(loaded.geometry.values()))
    if not isinstance(loaded, trimesh.Trimesh):
        raise HTTPException(status_code=422, detail="Unsupported mesh")
    return loaded


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/projects", response_model=ProjectInfo)
def create_project(payload: ProjectCreate) -> ProjectInfo:
    project_id = uuid.uuid4().hex[:12]
    root = PROJECT_ROOT / project_id
    (root / "images").mkdir(parents=True)
    (root / "meshes").mkdir()
    (root / "exports").mkdir()
    (root / "name.txt").write_text(payload.name.strip() or "Untitled project", encoding="utf-8")
    return ProjectInfo(id=project_id, name=payload.name.strip() or "Untitled project", image_count=0, mesh_available=False)


@app.get("/api/projects/{project_id}", response_model=ProjectInfo)
def get_project(project_id: str) -> ProjectInfo:
    root = project_dir(project_id)
    name = (root / "name.txt").read_text(encoding="utf-8")
    image_count = len(list((root / "images").glob("*")))
    mesh_available = any((root / "meshes").glob("*"))
    return ProjectInfo(id=project_id, name=name, image_count=image_count, mesh_available=mesh_available)


@app.post("/api/projects/{project_id}/images")
async def upload_images(project_id: str, files: Annotated[list[UploadFile], File()]) -> dict[str, int]:
    root = project_dir(project_id) / "images"
    accepted = 0
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_IMAGES:
            continue
        target = root / f"{uuid.uuid4().hex}{suffix}"
        with target.open("wb") as output:
            shutil.copyfileobj(file.file, output)
        accepted += 1
    if accepted == 0:
        raise HTTPException(status_code=400, detail="No supported images were uploaded")
    return {"accepted": accepted, "total": len(list(root.glob('*')))}


@app.post("/api/projects/{project_id}/mesh")
async def upload_mesh(project_id: str, file: Annotated[UploadFile, File()]) -> dict[str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_MESHES:
        raise HTTPException(status_code=400, detail="Unsupported mesh format")
    target = project_dir(project_id) / "meshes" / f"source{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    load_mesh(target)
    return {"status": "ready", "mesh": target.name}


@app.post("/api/projects/{project_id}/reconstruct")
def reconstruct(project_id: str) -> dict[str, str]:
    root = project_dir(project_id)
    images = list((root / "images").glob("*"))
    if len(images) < 20:
        raise HTTPException(status_code=400, detail="V1 reconstruction requires at least 20 photos")
    meshroom = shutil.which("meshroom_batch")
    if meshroom is None:
        raise HTTPException(status_code=503, detail="Meshroom/AliceVision is not installed or not on PATH")
    output = root / "reconstruction"
    output.mkdir(exist_ok=True)
    subprocess.Popen([meshroom, "--input", str(root / "images"), "--output", str(output)])
    return {"status": "started", "message": "Meshroom reconstruction started"}


@app.get("/api/projects/{project_id}/analysis")
def analyse_mesh(project_id: str) -> dict[str, object]:
    mesh = load_mesh(mesh_path(project_id))
    extents = [round(float(value), 3) for value in mesh.extents]
    return {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "volume": round(float(abs(mesh.volume)), 3) if mesh.is_volume else None,
        "bounds_mm": extents,
    }


@app.post("/api/projects/{project_id}/repair")
def repair_mesh(project_id: str) -> dict[str, object]:
    mesh = load_mesh(mesh_path(project_id))
    mesh.remove_unreferenced_vertices()
    mesh.remove_infinite_values()
    mesh.merge_vertices()
    trimesh.repair.fix_normals(mesh, multibody=True)
    trimesh.repair.fill_holes(mesh)
    target = project_dir(project_id) / "meshes" / "repaired.stl"
    mesh.export(target)
    return {"status": "repaired", "watertight": bool(mesh.is_watertight)}


@app.post("/api/projects/{project_id}/scale")
def scale_mesh(project_id: str, payload: ScaleRequest) -> dict[str, float]:
    if payload.current_mm <= 0 or payload.target_mm <= 0:
        raise HTTPException(status_code=400, detail="Measurements must be greater than zero")
    factor = payload.target_mm / payload.current_mm
    mesh = load_mesh(mesh_path(project_id))
    mesh.apply_scale(factor)
    target = project_dir(project_id) / "meshes" / "scaled.stl"
    mesh.export(target)
    return {"scale_factor": factor}


@app.get("/api/projects/{project_id}/mesh-preview")
def preview_mesh(project_id: str) -> FileResponse:
    source = mesh_path(project_id)
    mesh = load_mesh(source)
    preview = project_dir(project_id) / "meshes" / "preview.glb"
    mesh.export(preview)
    return FileResponse(preview, media_type="model/gltf-binary", filename="preview.glb")


@app.get("/api/projects/{project_id}/export/stl")
def export_stl(project_id: str) -> FileResponse:
    mesh = load_mesh(mesh_path(project_id))
    target = project_dir(project_id) / "exports" / "CCSDESIGN-Rebuild.stl"
    mesh.export(target)
    return FileResponse(target, media_type="model/stl", filename="CCSDESIGN-Rebuild.stl")
