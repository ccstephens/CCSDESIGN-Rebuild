from __future__ import annotations

import json
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import trimesh
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

APP_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = APP_ROOT / "data" / "projects"
ALLOWED_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
ALLOWED_MESHES = {".obj", ".ply", ".stl", ".glb", ".gltf"}
PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="CCSDESIGN Rebuild API", version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

class ProjectCreate(BaseModel): name:str
class ScaleRequest(BaseModel): current_mm:float; target_mm:float
class ProjectInfo(BaseModel): id:str; name:str; image_count:int; mesh_available:bool

def project_dir(project_id:str)->Path:
    path=PROJECT_ROOT/project_id
    if not path.exists(): raise HTTPException(404,"Project not found")
    return path

def job_file(project_id:str)->Path: return project_dir(project_id)/"reconstruction-job.json"
def write_job(project_id:str,**values:object)->dict[str,object]:
    path=job_file(project_id)
    data={"status":"idle","stage":"Waiting","progress":0,"message":"Ready","started_at":None,"finished_at":None}
    if path.exists():
        try: data.update(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError,OSError): pass
    data.update(values); path.write_text(json.dumps(data,indent=2),encoding="utf-8"); return data

def mesh_path(project_id:str)->Path:
    meshes=project_dir(project_id)/"meshes"
    for name in ("scaled.stl","repaired.stl","reconstruction.obj","reconstruction.ply","source.stl","source.obj","source.ply","source.glb","source.gltf"):
        candidate=meshes/name
        if candidate.exists(): return candidate
    raise HTTPException(404,"No mesh is available for this project yet")

def load_mesh(path:Path)->trimesh.Trimesh:
    loaded=trimesh.load(path,force="mesh")
    if isinstance(loaded,trimesh.Scene):
        if not loaded.geometry: raise HTTPException(422,"Mesh contains no geometry")
        loaded=trimesh.util.concatenate(tuple(loaded.geometry.values()))
    if not isinstance(loaded,trimesh.Trimesh): raise HTTPException(422,"Unsupported mesh")
    return loaded

def find_reconstructed_mesh(root:Path)->Path|None:
    candidates=[]
    for pattern in ("**/texturedMesh.obj","**/mesh.obj","**/*.obj","**/*.ply"):
        candidates.extend(root.glob(pattern))
    return max(candidates,key=lambda p:p.stat().st_size) if candidates else None

def run_reconstruction(project_id:str,meshroom:str)->None:
    root=project_dir(project_id); output=root/"reconstruction"; log_path=root/"reconstruction.log"
    write_job(project_id,status="running",stage="Feature extraction",progress=5,message="Meshroom is matching features across your photos.")
    try:
        with log_path.open("w",encoding="utf-8",errors="replace") as log:
            process=subprocess.Popen([meshroom,"--input",str(root/"images"),"--output",str(output)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line); low=line.lower()
                if "featurematching" in low: write_job(project_id,status="running",stage="Photo matching",progress=20,message="Finding matching points between photographs.")
                elif "structurefrommotion" in low: write_job(project_id,status="running",stage="Camera solve",progress=35,message="Calculating camera positions and object structure.")
                elif "depthmap" in low: write_job(project_id,status="running",stage="Depth maps",progress=55,message="Building detailed depth information.")
                elif "meshing" in low: write_job(project_id,status="running",stage="Meshing",progress=75,message="Turning the scan into 3D geometry.")
                elif "meshfiltering" in low: write_job(project_id,status="running",stage="Mesh cleanup",progress=88,message="Cleaning reconstructed geometry.")
                elif "texturing" in low: write_job(project_id,status="running",stage="Finalising",progress=95,message="Finalising the reconstructed model.")
            code=process.wait()
        if code!=0:
            write_job(project_id,status="failed",stage="Failed",progress=0,message=f"Meshroom stopped with exit code {code}. See reconstruction.log.",finished_at=datetime.now(timezone.utc).isoformat()); return
        found=find_reconstructed_mesh(output)
        if found is None:
            write_job(project_id,status="failed",stage="No mesh produced",progress=0,message="Meshroom finished but no OBJ/PLY mesh was found.",finished_at=datetime.now(timezone.utc).isoformat()); return
        suffix=found.suffix.lower(); target=root/"meshes"/f"reconstruction{suffix}"; shutil.copy2(found,target)
        write_job(project_id,status="complete",stage="Complete",progress=100,message="3D reconstruction complete. The model is ready to inspect and repair.",finished_at=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        write_job(project_id,status="failed",stage="Failed",progress=0,message=f"Reconstruction error: {exc}",finished_at=datetime.now(timezone.utc).isoformat())

@app.get("/api/health")
def health()->dict[str,str]: return {"status":"ok","version":"0.1.0"}
@app.post("/api/projects",response_model=ProjectInfo)
def create_project(payload:ProjectCreate)->ProjectInfo:
    project_id=uuid.uuid4().hex[:12]; root=PROJECT_ROOT/project_id
    (root/"images").mkdir(parents=True); (root/"meshes").mkdir(); (root/"exports").mkdir()
    name=payload.name.strip() or "Untitled project"; (root/"name.txt").write_text(name,encoding="utf-8"); write_job(project_id)
    return ProjectInfo(id=project_id,name=name,image_count=0,mesh_available=False)
@app.get("/api/projects/{project_id}",response_model=ProjectInfo)
def get_project(project_id:str)->ProjectInfo:
    root=project_dir(project_id); return ProjectInfo(id=project_id,name=(root/"name.txt").read_text(encoding="utf-8"),image_count=len(list((root/"images").glob("*"))),mesh_available=any((root/"meshes").glob("*")))
@app.post("/api/projects/{project_id}/images")
async def upload_images(project_id:str,files:Annotated[list[UploadFile],File()])->dict[str,int]:
    root=project_dir(project_id)/"images"; accepted=0
    for file in files:
        suffix=Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_IMAGES: continue
        with (root/f"{uuid.uuid4().hex}{suffix}").open("wb") as output: shutil.copyfileobj(file.file,output)
        accepted+=1
    if accepted==0: raise HTTPException(400,"No supported images were uploaded")
    return {"accepted":accepted,"total":len(list(root.glob('*')))}
@app.post("/api/projects/{project_id}/mesh")
async def upload_mesh(project_id:str,file:Annotated[UploadFile,File()])->dict[str,str]:
    suffix=Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_MESHES: raise HTTPException(400,"Unsupported mesh format")
    target=project_dir(project_id)/"meshes"/f"source{suffix}"
    with target.open("wb") as output: shutil.copyfileobj(file.file,output)
    load_mesh(target); return {"status":"ready","mesh":target.name}
@app.post("/api/projects/{project_id}/reconstruct")
def reconstruct(project_id:str)->dict[str,str]:
    root=project_dir(project_id); images=list((root/"images").glob("*"))
    if len(images)<20: raise HTTPException(400,"V1 reconstruction requires at least 20 photos")
    current=write_job(project_id)
    if current.get("status")=="running": raise HTTPException(409,"A reconstruction is already running")
    meshroom=shutil.which("meshroom_batch")
    if meshroom is None: raise HTTPException(503,"Meshroom/AliceVision is not installed or not on PATH")
    (root/"reconstruction").mkdir(exist_ok=True)
    write_job(project_id,status="queued",stage="Starting",progress=1,message="Preparing photographs for Meshroom.",started_at=datetime.now(timezone.utc).isoformat(),finished_at=None)
    threading.Thread(target=run_reconstruction,args=(project_id,meshroom),daemon=True).start()
    return {"status":"started","message":"Reconstruction started. Progress is now being tracked."}
@app.get("/api/projects/{project_id}/reconstruct/status")
def reconstruction_status(project_id:str)->dict[str,object]: return write_job(project_id)
@app.get("/api/projects/{project_id}/analysis")
def analyse_mesh(project_id:str)->dict[str,object]:
    mesh=load_mesh(mesh_path(project_id)); extents=[round(float(v),3) for v in mesh.extents]
    return {"vertices":int(len(mesh.vertices)),"faces":int(len(mesh.faces)),"watertight":bool(mesh.is_watertight),"winding_consistent":bool(mesh.is_winding_consistent),"volume":round(float(abs(mesh.volume)),3) if mesh.is_volume else None,"bounds_mm":extents}
@app.post("/api/projects/{project_id}/repair")
def repair_mesh(project_id:str)->dict[str,object]:
    mesh=load_mesh(mesh_path(project_id)); mesh.remove_unreferenced_vertices(); mesh.remove_infinite_values(); mesh.merge_vertices(); trimesh.repair.fix_normals(mesh,multibody=True); trimesh.repair.fill_holes(mesh)
    target=project_dir(project_id)/"meshes"/"repaired.stl"; mesh.export(target); return {"status":"repaired","watertight":bool(mesh.is_watertight)}
@app.post("/api/projects/{project_id}/scale")
def scale_mesh(project_id:str,payload:ScaleRequest)->dict[str,float]:
    if payload.current_mm<=0 or payload.target_mm<=0: raise HTTPException(400,"Measurements must be greater than zero")
    factor=payload.target_mm/payload.current_mm; mesh=load_mesh(mesh_path(project_id)); mesh.apply_scale(factor); mesh.export(project_dir(project_id)/"meshes"/"scaled.stl"); return {"scale_factor":factor}
@app.get("/api/projects/{project_id}/mesh-preview")
def preview_mesh(project_id:str)->FileResponse:
    mesh=load_mesh(mesh_path(project_id)); preview=project_dir(project_id)/"meshes"/"preview.glb"; mesh.export(preview); return FileResponse(preview,media_type="model/gltf-binary",filename="preview.glb")
@app.get("/api/projects/{project_id}/export/stl")
def export_stl(project_id:str)->FileResponse:
    mesh=load_mesh(mesh_path(project_id)); target=project_dir(project_id)/"exports"/"CCSDESIGN-Rebuild.stl"; mesh.export(target); return FileResponse(target,media_type="model/stl",filename="CCSDESIGN-Rebuild.stl")
