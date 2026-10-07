from __future__ import annotations
import json,shutil,subprocess,threading,uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Annotated
import numpy as np
import trimesh
from fastapi import FastAPI,File,HTTPException,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .repair import create_mirrored_repair,create_selected_mirrored_repair
APP_ROOT=Path(__file__).resolve().parents[2];PROJECT_ROOT=APP_ROOT/'data'/'projects';ALLOWED_IMAGES={'.jpg','.jpeg','.png','.webp','.tif','.tiff'};ALLOWED_MESHES={'.obj','.ply','.stl','.glb','.gltf'};PROJECT_ROOT.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='CCSDESIGN Rebuild API',version='0.1.0');app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
class ProjectCreate(BaseModel):name:str
class ScaleRequest(BaseModel):current_mm:float;target_mm:float
class MissingPartRequest(BaseModel):axis:str='x';keep_side:str='positive';overlap_mm:float=0.4
class SelectedRepairRequest(BaseModel):axis:str='x';point:list[float];radius_mm:float;overlap_mm:float=0.4
class ProjectInfo(BaseModel):id:str;name:str;image_count:int;mesh_available:bool
def project_dir(i:str)->Path:
 p=PROJECT_ROOT/i
 if not p.exists():raise HTTPException(404,'Project not found')
 return p
def job_file(i):return project_dir(i)/'reconstruction-job.json'
def write_job(i,**v):
 p=job_file(i);d={'status':'idle','stage':'Waiting','progress':0,'message':'Ready','started_at':None,'finished_at':None}
 if p.exists():
  try:d.update(json.loads(p.read_text(encoding='utf-8')))
  except (json.JSONDecodeError,OSError):pass
 d.update(v);p.write_text(json.dumps(d,indent=2),encoding='utf-8');return d
def mesh_path(i):
 m=project_dir(i)/'meshes'
 for n in ('missing-part-repair.stl','scaled.stl','repaired.stl','reconstruction.obj','reconstruction.ply','source.stl','source.obj','source.ply','source.glb','source.gltf'):
  p=m/n
  if p.exists():return p
 raise HTTPException(404,'No mesh is available for this project yet')
def source_for_missing_repair(i):
 m=project_dir(i)/'meshes'
 for n in ('scaled.stl','repaired.stl','reconstruction.obj','reconstruction.ply','source.stl','source.obj','source.ply','source.glb','source.gltf'):
  p=m/n
  if p.exists():return p
 raise HTTPException(404,'No source mesh is available for missing-part repair')
def load_mesh(p):
 x=trimesh.load(p,force='mesh')
 if isinstance(x,trimesh.Scene):
  if not x.geometry:raise HTTPException(422,'Mesh contains no geometry')
  x=trimesh.util.concatenate(tuple(x.geometry.values()))
 if not isinstance(x,trimesh.Trimesh):raise HTTPException(422,'Unsupported mesh')
 return x
def find_reconstructed_mesh(root):
 c=[]
 for pattern in ('**/texturedMesh.obj','**/mesh.obj','**/*.obj','**/*.ply'):c.extend(root.glob(pattern))
 return max(c,key=lambda p:p.stat().st_size) if c else None
def run_reconstruction(i,meshroom):
 root=project_dir(i);out=root/'reconstruction';log=root/'reconstruction.log';write_job(i,status='running',stage='Feature extraction',progress=5,message='Meshroom is matching features across your photos.')
 try:
  with log.open('w',encoding='utf-8',errors='replace') as f:
   p=subprocess.Popen([meshroom,'--input',str(root/'images'),'--output',str(out)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1);assert p.stdout
   for line in p.stdout:
    f.write(line);low=line.lower();stages=[('featurematching','Photo matching',20,'Finding matching points between photographs.'),('structurefrommotion','Camera solve',35,'Calculating camera positions and object structure.'),('depthmap','Depth maps',55,'Building detailed depth information.'),('meshing','Meshing',75,'Turning the scan into 3D geometry.'),('meshfiltering','Mesh cleanup',88,'Cleaning reconstructed geometry.'),('texturing','Finalising',95,'Finalising the reconstructed model.')]
    for key,stage,progress,msg in stages:
     if key in low:write_job(i,status='running',stage=stage,progress=progress,message=msg);break
   code=p.wait()
  if code!=0:write_job(i,status='failed',stage='Failed',progress=0,message=f'Meshroom stopped with exit code {code}. See reconstruction.log.',finished_at=datetime.now(timezone.utc).isoformat());return
  found=find_reconstructed_mesh(out)
  if not found:write_job(i,status='failed',stage='No mesh produced',progress=0,message='Meshroom finished but no OBJ/PLY mesh was found.',finished_at=datetime.now(timezone.utc).isoformat());return
  shutil.copy2(found,root/'meshes'/f'reconstruction{found.suffix.lower()}');write_job(i,status='complete',stage='Complete',progress=100,message='3D reconstruction complete. The model is ready to inspect and repair.',finished_at=datetime.now(timezone.utc).isoformat())
 except Exception as e:write_job(i,status='failed',stage='Failed',progress=0,message=f'Reconstruction error: {e}',finished_at=datetime.now(timezone.utc).isoformat())
def analyse(i):
 m=load_mesh(mesh_path(i));ext=[round(float(v),3) for v in m.extents];components=len(m.split(only_watertight=False));areas=np.asarray(m.area_faces);degenerate=int(np.count_nonzero(areas<1e-10));checks=[]
 def add(name,state,message):checks.append({'name':name,'state':state,'message':message})
 add('Closed mesh','pass' if m.is_watertight else 'fail','Mesh is watertight.' if m.is_watertight else 'Open edges or holes detected; repair before printing.');add('Normals','pass' if m.is_winding_consistent else 'warning','Face directions are consistent.' if m.is_winding_consistent else 'Inconsistent face directions detected.');add('Separate parts','pass' if components==1 else 'warning',f'{components} connected component(s) detected.');add('Degenerate faces','pass' if degenerate==0 else 'warning',f'{degenerate} near-zero-area face(s) detected.');add('Physical size','pass' if min(ext)>0.1 else 'fail',f'Model bounds: {" × ".join(map(str,ext))} mm.');overall='fail' if any(c['state']=='fail' for c in checks) else ('warning' if any(c['state']=='warning' for c in checks) else 'pass')
 return {'vertices':int(len(m.vertices)),'faces':int(len(m.faces)),'watertight':bool(m.is_watertight),'winding_consistent':bool(m.is_winding_consistent),'volume':round(float(abs(m.volume)),3) if m.is_volume else None,'bounds_mm':ext,'components':components,'degenerate_faces':degenerate,'printability':{'overall':overall,'checks':checks}}
@app.get('/api/health')
def health():return {'status':'ok','version':'0.1.0'}
@app.post('/api/projects',response_model=ProjectInfo)
def create_project(x:ProjectCreate):
 i=uuid.uuid4().hex[:12];r=PROJECT_ROOT/i;(r/'images').mkdir(parents=True);(r/'meshes').mkdir();(r/'exports').mkdir();n=x.name.strip()or'Untitled project';(r/'name.txt').write_text(n,encoding='utf-8');write_job(i);return ProjectInfo(id=i,name=n,image_count=0,mesh_available=False)
@app.get('/api/projects/{i}',response_model=ProjectInfo)
def get_project(i):
 r=project_dir(i);return ProjectInfo(id=i,name=(r/'name.txt').read_text(),image_count=len(list((r/'images').glob('*'))),mesh_available=any((r/'meshes').glob('*')))
@app.post('/api/projects/{i}/images')
async def upload_images(i,files:Annotated[list[UploadFile],File()]):
 r=project_dir(i)/'images';a=0
 for f in files:
  s=Path(f.filename or'').suffix.lower()
  if s not in ALLOWED_IMAGES:continue
  with(r/f'{uuid.uuid4().hex}{s}').open('wb')as o:shutil.copyfileobj(f.file,o)
  a+=1
 if not a:raise HTTPException(400,'No supported images were uploaded')
 return {'accepted':a,'total':len(list(r.glob('*')))}
@app.post('/api/projects/{i}/mesh')
async def upload_mesh(i,file:Annotated[UploadFile,File()]):
 s=Path(file.filename or'').suffix.lower()
 if s not in ALLOWED_MESHES:raise HTTPException(400,'Unsupported mesh format')
 t=project_dir(i)/'meshes'/f'source{s}'
 with t.open('wb')as o:shutil.copyfileobj(file.file,o)
 load_mesh(t);return {'status':'ready','mesh':t.name}
@app.post('/api/projects/{i}/reconstruct')
def reconstruct(i):
 r=project_dir(i)
 if len(list((r/'images').glob('*')))<20:raise HTTPException(400,'V1 reconstruction requires at least 20 photos')
 if write_job(i).get('status')=='running':raise HTTPException(409,'A reconstruction is already running')
 mr=shutil.which('meshroom_batch')
 if not mr:raise HTTPException(503,'Meshroom/AliceVision is not installed or not on PATH')
 (r/'reconstruction').mkdir(exist_ok=True);write_job(i,status='queued',stage='Starting',progress=1,message='Preparing photographs for Meshroom.',started_at=datetime.now(timezone.utc).isoformat(),finished_at=None);threading.Thread(target=run_reconstruction,args=(i,mr),daemon=True).start();return {'status':'started','message':'Reconstruction started. Progress is now being tracked.'}
@app.get('/api/projects/{i}/reconstruct/status')
def reconstruction_status(i):return write_job(i)
@app.get('/api/projects/{i}/analysis')
def analyse_mesh(i):return analyse(i)
@app.post('/api/projects/{i}/repair')
def repair_mesh(i):
 m=load_mesh(mesh_path(i));m.remove_unreferenced_vertices();m.remove_infinite_values();m.merge_vertices();trimesh.repair.fix_normals(m,multibody=True);trimesh.repair.fill_holes(m);m.export(project_dir(i)/'meshes'/'repaired.stl');return {'status':'repaired','watertight':bool(m.is_watertight)}
@app.post('/api/projects/{i}/missing-part/preview')
def missing_part_preview(i,x:MissingPartRequest):
 try:patch,combined,plane=create_mirrored_repair(load_mesh(source_for_missing_repair(i)),x.axis,x.keep_side,x.overlap_mm)
 except ValueError as e:raise HTTPException(400,str(e))
 r=project_dir(i)/'meshes';patch.export(r/'missing-part-patch.stl');combined.export(r/'missing-part-preview.glb');return {'status':'preview','plane_mm':round(plane,3),'patch_faces':int(len(patch.faces)),'message':'Missing-part preview generated. Inspect it before applying.'}
@app.post('/api/projects/{i}/missing-part/selected-preview')
def selected_missing_part_preview(i,x:SelectedRepairRequest):
 try:patch,combined,plane,donor_faces=create_selected_mirrored_repair(load_mesh(source_for_missing_repair(i)),x.axis,x.point,x.radius_mm,x.overlap_mm)
 except ValueError as e:raise HTTPException(400,str(e))
 r=project_dir(i)/'meshes';patch.export(r/'missing-part-patch.stl');combined.export(r/'missing-part-preview.glb');return {'status':'preview','plane_mm':round(plane,3),'patch_faces':int(len(patch.faces)),'donor_faces':donor_faces,'message':'Selected damaged area rebuilt from matching geometry on the opposite side. Inspect the highlighted-area repair before applying.'}
@app.get('/api/projects/{i}/missing-part/preview')
def missing_part_preview_file(i):
 p=project_dir(i)/'meshes'/'missing-part-preview.glb'
 if not p.exists():raise HTTPException(404,'Generate a missing-part preview first')
 return FileResponse(p,media_type='model/gltf-binary',filename='missing-part-preview.glb')
@app.post('/api/projects/{i}/missing-part/apply')
def missing_part_apply(i):
 r=project_dir(i)/'meshes';patch=r/'missing-part-patch.stl'
 if not patch.exists():raise HTTPException(404,'Generate and inspect a missing-part preview first')
 combined=trimesh.util.concatenate((load_mesh(source_for_missing_repair(i)),load_mesh(patch)));combined.merge_vertices();combined.remove_unreferenced_vertices();trimesh.repair.fix_normals(combined,multibody=True);trimesh.repair.fill_holes(combined);target=r/'missing-part-repair.stl';combined.export(target);return {'status':'applied','watertight':bool(combined.is_watertight),'components':len(combined.split(only_watertight=False)),'message':'Missing-part repair applied. Run printability analysis before export.'}
@app.post('/api/projects/{i}/scale')
def scale_mesh(i,x:ScaleRequest):
 if x.current_mm<=0 or x.target_mm<=0:raise HTTPException(400,'Measurements must be greater than zero')
 f=x.target_mm/x.current_mm;m=load_mesh(mesh_path(i));m.apply_scale(f);m.export(project_dir(i)/'meshes'/'scaled.stl');return {'scale_factor':f}
@app.get('/api/projects/{i}/mesh-preview')
def preview_mesh(i):
 m=load_mesh(mesh_path(i));p=project_dir(i)/'meshes'/'preview.glb';m.export(p);return FileResponse(p,media_type='model/gltf-binary',filename='preview.glb')
@app.get('/api/projects/{i}/export/stl')
def export_stl(i):
 report=analyse(i)
 if report['printability']['overall']=='fail':raise HTTPException(409,'Export blocked: fix failed printability checks first')
 m=load_mesh(mesh_path(i));t=project_dir(i)/'exports'/'CCSDESIGN-Rebuild.stl';m.export(t);return FileResponse(t,media_type='model/stl',filename='CCSDESIGN-Rebuild.stl')
