from __future__ import annotations
import json,shutil,subprocess,threading,uuid,os,sys
from datetime import datetime,timezone
from pathlib import Path
from typing import Annotated
import numpy as np
import trimesh
from fastapi import FastAPI,File,HTTPException,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .repair import create_mirrored_repair,create_selected_mirrored_repair
SOURCE_ROOT=Path(__file__).resolve().parents[2];BUNDLE_ROOT=Path(getattr(sys,'_MEIPASS',SOURCE_ROOT));DATA_ROOT=(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'CCSDESIGN Rebuild') if getattr(sys,'frozen',False) else SOURCE_ROOT/'data';PROJECT_ROOT=DATA_ROOT/'projects';ALLOWED_IMAGES={'.jpg','.jpeg','.png','.webp','.tif','.tiff'};ALLOWED_MESHES={'.obj','.ply','.stl','.glb','.gltf'};PROJECT_ROOT.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='CCSDESIGN Rebuild API',version='0.1.0');app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
class ProjectCreate(BaseModel):name:str
class ProjectRename(BaseModel):name:str
class ScaleRequest(BaseModel):current_mm:float;target_mm:float
class MissingPartRequest(BaseModel):axis:str='x';keep_side:str='positive';overlap_mm:float=0.4
class SelectedRepairRequest(BaseModel):axis:str='x';point:list[float];radius_mm:float;overlap_mm:float=0.4
class ProjectInfo(BaseModel):id:str;name:str;image_count:int;mesh_available:bool
MESH_NAMES=('missing-part-repair.stl','scaled.stl','repaired.stl','reconstruction.obj','reconstruction.ply','source.stl','source.obj','source.ply','source.glb','source.gltf')
def meshroom_path():
 configured=os.environ.get('MESHROOM_BATCH','').strip()
 if configured:
  p=Path(configured).expanduser()
  if p.is_file():return str(p)
 p=shutil.which('meshroom_batch')
 if p:return p
 if os.name=='nt':
  roots=[Path(os.environ.get('ProgramFiles','C:/Program Files')),Path(os.environ.get('LOCALAPPDATA',Path.home()))]
  patterns=('Meshroom*/meshroom_batch.exe','Meshroom*/meshroom_batch.bat','AliceVision*/meshroom_batch.exe')
  for root in roots:
   for pattern in patterns:
    matches=sorted(root.glob(pattern),reverse=True)
    if matches:return str(matches[0])
 return None
def project_dir(i:str)->Path:
 p=PROJECT_ROOT/i
 if not p.exists():raise HTTPException(404,'Project not found')
 return p
def job_file(i):return project_dir(i)/'reconstruction-job.json'
def pid_alive(pid,expected_started=None):
 if not isinstance(pid,int) or pid<=0:return False
 try:
  import psutil
  p=psutil.Process(pid)
  if not p.is_running():return False
  if expected_started:
   started=datetime.fromtimestamp(p.create_time(),timezone.utc)
   expected=datetime.fromisoformat(expected_started)
   if abs((started-expected).total_seconds())>5:return False
  return True
 except Exception:return False
def recover_job(i):
 d=write_job(i)
 if d.get('status') in {'queued','running'} and not pid_alive(d.get('pid'),d.get('process_started_at')):
  return write_job(i,status='failed',stage='Interrupted',progress=0,message='The previous reconstruction was interrupted when the app stopped. Start reconstruction again to retry.',finished_at=datetime.now(timezone.utc).isoformat(),pid=None,process_started_at=None)
 return d
def clear_derived(i,keep=()):
 r=project_dir(i);m=r/'meshes';e=r/'exports';names={'repaired.stl','scaled.stl','missing-part-patch.stl','missing-part-preview.glb','missing-part-repair.stl','missing-part-candidate.stl','preview.glb'}-set(keep)
 for n in names:
  p=m/n
  if p.exists():p.unlink()
 for p in e.glob('*'):
  if p.is_file():p.unlink()
def write_job(i,**v):
 p=job_file(i);d={'status':'idle','stage':'Waiting','progress':0,'message':'Ready','started_at':None,'finished_at':None}
 if p.exists():
  try:d.update(json.loads(p.read_text(encoding='utf-8')))
  except (json.JSONDecodeError,OSError):pass
 d.update(v);p.write_text(json.dumps(d,indent=2),encoding='utf-8');return d
def clear_missing_preview(i):
 r=project_dir(i)/'meshes'
 for n in ('missing-part-patch.stl','missing-part-preview.glb','missing-part-candidate.stl'):
  (r/n).unlink(missing_ok=True)
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
 try:x=trimesh.load(p,force='mesh')
 except HTTPException:raise
 except Exception as e:raise HTTPException(422,f'Could not read mesh: {e}') from e
 if isinstance(x,trimesh.Scene):
  if not x.geometry:raise HTTPException(422,'Mesh contains no geometry')
  x=trimesh.util.concatenate(tuple(x.geometry.values()))
 if not isinstance(x,trimesh.Trimesh):raise HTTPException(422,'Unsupported mesh')
 if len(x.vertices)==0 or len(x.faces)==0:raise HTTPException(422,'Mesh contains no usable geometry')
 return x
def find_reconstructed_mesh(root):
 c=[]
 for pattern in ('**/texturedMesh.obj','**/mesh.obj','**/*.obj','**/*.ply'):c.extend(root.glob(pattern))
 c=list(set(c));return max(c,key=lambda p:p.stat().st_size) if c else None
def run_reconstruction(i,meshroom):
 root=project_dir(i);out=root/'reconstruction';log=root/'reconstruction.log';shutil.rmtree(out,ignore_errors=True);out.mkdir(parents=True,exist_ok=True);write_job(i,status='running',stage='Feature extraction',progress=5,message='Meshroom is matching features across your photos.')
 try:
  with log.open('w',encoding='utf-8',errors='replace') as f:
   p=subprocess.Popen([meshroom,'--input',str(root/'images'),'--output',str(out)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1);write_job(i,pid=p.pid,process_started_at=datetime.fromtimestamp(psutil.Process(p.pid).create_time(),timezone.utc).isoformat());assert p.stdout
   for line in p.stdout:
    f.write(line);low=line.lower();stages=[('featurematching','Photo matching',20,'Finding matching points between photographs.'),('structurefrommotion','Camera solve',35,'Calculating camera positions and object structure.'),('depthmap','Depth maps',55,'Building detailed depth information.'),('meshing','Meshing',75,'Turning the scan into 3D geometry.'),('meshfiltering','Mesh cleanup',88,'Cleaning reconstructed geometry.'),('texturing','Finalising',95,'Finalising the reconstructed model.')]
    for key,stage,progress,msg in stages:
     if key in low:write_job(i,status='running',stage=stage,progress=progress,message=msg);break
   code=p.wait()
  if code!=0:write_job(i,status='failed',stage='Failed',progress=0,message=f'Meshroom stopped with exit code {code}. See reconstruction.log.',finished_at=datetime.now(timezone.utc).isoformat(),pid=None);return
  found=find_reconstructed_mesh(out)
  if not found:write_job(i,status='failed',stage='No mesh produced',progress=0,message='Meshroom finished but no OBJ/PLY mesh was found.',finished_at=datetime.now(timezone.utc).isoformat(),pid=None);return
  clear_derived(i);meshes=root/'meshes';(meshes/'reconstruction.obj').unlink(missing_ok=True);(meshes/'reconstruction.ply').unlink(missing_ok=True);shutil.copy2(found,meshes/f'reconstruction{found.suffix.lower()}');write_job(i,status='complete',stage='Complete',progress=100,message='3D reconstruction complete. The model is ready to inspect and repair.',finished_at=datetime.now(timezone.utc).isoformat(),pid=None)
 except Exception as e:write_job(i,status='failed',stage='Failed',progress=0,message=f'Reconstruction error: {e}',finished_at=datetime.now(timezone.utc).isoformat(),pid=None)
def analyse(i):
 m=load_mesh(mesh_path(i));ext=[round(float(v),3) for v in m.extents];components=len(m.split(only_watertight=False));areas=np.asarray(m.area_faces);degenerate=int(np.count_nonzero(areas<1e-10));edge_counts=np.bincount(m.edges_unique_inverse) if len(m.edges_unique_inverse) else np.array([],dtype=int);boundary_edges=int(np.count_nonzero(edge_counts==1));non_manifold_edges=int(np.count_nonzero(edge_counts>2));checks=[]
 def add(name,state,message):checks.append({'name':name,'state':state,'message':message})
 add('Closed mesh','pass' if boundary_edges==0 else 'fail','No boundary edges detected.' if boundary_edges==0 else f'{boundary_edges} boundary edge(s) detected; the model is open.');add('Manifold edges','pass' if non_manifold_edges==0 else 'fail','Every edge has a printable manifold connection.' if non_manifold_edges==0 else f'{non_manifold_edges} non-manifold edge(s) detected.');add('Normals','pass' if m.is_winding_consistent else 'warning','Face directions are consistent.' if m.is_winding_consistent else 'Inconsistent face directions detected.');add('Separate parts','pass' if components==1 else 'warning',f'{components} connected component(s) detected.');add('Degenerate faces','pass' if degenerate==0 else 'warning',f'{degenerate} near-zero-area face(s) detected.');add('Physical size','pass' if min(ext)>0.1 else 'fail',f'Model bounds: {" × ".join(map(str,ext))} mm.');overall='fail' if any(c['state']=='fail' for c in checks) else ('warning' if any(c['state']=='warning' for c in checks) else 'pass')
 return {'vertices':int(len(m.vertices)),'faces':int(len(m.faces)),'watertight':bool(m.is_watertight),'winding_consistent':bool(m.is_winding_consistent),'volume':round(float(abs(m.volume)),3) if m.is_volume else None,'bounds_mm':ext,'components':components,'degenerate_faces':degenerate,'boundary_edges':boundary_edges,'non_manifold_edges':non_manifold_edges,'printability':{'overall':overall,'checks':checks}}
@app.get('/api/health')
def health():
 mr=meshroom_path()
 return {'status':'ok','version':'0.1.0','meshroom_available':bool(mr),'meshroom_path':mr}
@app.post('/api/projects',response_model=ProjectInfo)
def create_project(x:ProjectCreate):
 i=uuid.uuid4().hex[:12];r=PROJECT_ROOT/i;(r/'images').mkdir(parents=True);(r/'meshes').mkdir();(r/'exports').mkdir();n=x.name.strip()or'Untitled project';(r/'name.txt').write_text(n,encoding='utf-8');write_job(i);return ProjectInfo(id=i,name=n,image_count=0,mesh_available=False)
@app.get('/api/projects',response_model=list[ProjectInfo])
def list_projects():
 out=[]
 for r in PROJECT_ROOT.iterdir():
  if not r.is_dir():continue
  name=r/'name.txt'
  if not name.exists():continue
  out.append(ProjectInfo(id=r.name,name=name.read_text(encoding='utf-8'),image_count=len(list((r/'images').glob('*'))),mesh_available=any((r/'meshes'/n).exists() for n in ('missing-part-repair.stl','scaled.stl','repaired.stl','reconstruction.obj','reconstruction.ply','source.stl','source.obj','source.ply','source.glb','source.gltf'))))
 return sorted(out,key=lambda p:(PROJECT_ROOT/p.id).stat().st_mtime,reverse=True)
@app.patch('/api/projects/{i}',response_model=ProjectInfo)
def rename_project(i,x:ProjectRename):
 r=project_dir(i);name=x.name.strip()
 if not name:raise HTTPException(400,'Project name cannot be empty')
 if len(name)>80:raise HTTPException(400,'Project name must be 80 characters or fewer')
 (r/'name.txt').write_text(name,encoding='utf-8')
 return get_project(i)
@app.delete('/api/projects/{i}')
def delete_project(i):
 r=project_dir(i);job=recover_job(i)
 if job.get('status') in {'queued','running'}:raise HTTPException(409,'Cannot delete a project while reconstruction is running')
 shutil.rmtree(r)
 return {'status':'deleted','id':i}
@app.get('/api/projects/{i}',response_model=ProjectInfo)
def get_project(i):
 r=project_dir(i);return ProjectInfo(id=i,name=(r/'name.txt').read_text(),image_count=len(list((r/'images').glob('*'))),mesh_available=any((r/'meshes'/n).exists() for n in MESH_NAMES))
@app.delete('/api/projects/{i}/images')
def clear_images(i):
 r=project_dir(i);job=recover_job(i)
 if job.get('status') in {'queued','running'}:raise HTTPException(409,'Cannot change photos while reconstruction is running')
 images=r/'images';count=0
 for p in images.iterdir():
  if p.is_file():p.unlink();count+=1
 reconstruction=r/'reconstruction'
 if reconstruction.exists():shutil.rmtree(reconstruction)
 for p in (r/'meshes'/'reconstruction.obj',r/'meshes'/'reconstruction.ply'):
  p.unlink(missing_ok=True)
 write_job(i,status='idle',stage='Waiting',progress=0,message='Photos cleared. Add a new 20–50 photo set.',started_at=None,finished_at=None,pid=None)
 return {'status':'cleared','removed':count}
@app.post('/api/projects/{i}/images')
async def upload_images(i,files:Annotated[list[UploadFile],File()]):
 root=project_dir(i);job=recover_job(i)
 if job.get('status') in {'queued','running'}:raise HTTPException(409,'Cannot change photos while reconstruction is running')
 r=root/'images';supported=[f for f in files if Path(f.filename or'').suffix.lower() in ALLOWED_IMAGES]
 if not supported:raise HTTPException(400,'No supported images were uploaded')
 existing=len(list(r.glob('*')))
 if existing+len(supported)>50:raise HTTPException(400,f'V1 accepts a maximum of 50 photos. This project already has {existing}.')
 for f in supported:
  s=Path(f.filename or'').suffix.lower()
  with(r/f'{uuid.uuid4().hex}{s}').open('wb')as o:shutil.copyfileobj(f.file,o)
 write_job(i,status='idle',stage='Waiting',progress=0,message='Photo set changed. Ready to build a new 3D scan when 20–50 photos are loaded.',started_at=None,finished_at=None,pid=None,process_started_at=None)
 return {'accepted':len(supported),'total':existing+len(supported)}
@app.post('/api/projects/{i}/mesh')
async def upload_mesh(i,file:Annotated[UploadFile,File()]):
 s=Path(file.filename or'').suffix.lower()
 if s not in ALLOWED_MESHES:raise HTTPException(400,'Unsupported mesh format')
 m=project_dir(i)/'meshes';tmp=m/f'.upload-{uuid.uuid4().hex}{s}'
 try:
  with tmp.open('wb')as o:shutil.copyfileobj(file.file,o)
  candidate=load_mesh(tmp)
  if len(candidate.vertices)==0 or len(candidate.faces)==0:raise HTTPException(422,'Mesh contains no usable faces')
 except Exception:
  tmp.unlink(missing_ok=True)
  raise
 clear_derived(i)
 for old in m.glob('source.*'):
  if old.is_file():old.unlink()
 for old in (m/'reconstruction.obj',m/'reconstruction.ply'):
  if old.exists():old.unlink()
 t=m/f'source{s}';tmp.replace(t);return {'status':'ready','mesh':t.name}
@app.post('/api/projects/{i}/reconstruct')
def reconstruct(i):
 r=project_dir(i);count=len(list((r/'images').glob('*')))
 if count<20 or count>50:raise HTTPException(400,f'V1 reconstruction requires 20–50 photos; this project has {count}.')
 if recover_job(i).get('status') in {'queued','running'}:raise HTTPException(409,'A reconstruction is already running')
 mr=meshroom_path()
 if not mr:raise HTTPException(503,'Meshroom/AliceVision is not installed or not on PATH')
 shutil.rmtree(r/'reconstruction',ignore_errors=True);(r/'reconstruction').mkdir(exist_ok=True);(r/'reconstruction.log').unlink(missing_ok=True);write_job(i,status='queued',stage='Starting',progress=1,message='Preparing photographs for Meshroom.',started_at=datetime.now(timezone.utc).isoformat(),finished_at=None,pid=None,process_started_at=None);threading.Thread(target=run_reconstruction,args=(i,mr),daemon=True).start();return {'status':'started','message':'Reconstruction started. Progress is now being tracked.'}
@app.get('/api/projects/{i}/reconstruct/status')
def reconstruction_status(i):return recover_job(i)
@app.get('/api/projects/{i}/reconstruct/diagnostics')
def reconstruction_diagnostics(i):
 r=project_dir(i);job=recover_job(i);log=r/'reconstruction.log';tail=[]
 if log.exists():
  try:tail=log.read_text(encoding='utf-8',errors='replace').splitlines()[-40:]
  except OSError:tail=[]
 return {'status':job.get('status','idle'),'stage':job.get('stage','Waiting'),'message':job.get('message','Ready'),'meshroom_path':meshroom_path(),'photo_count':len(list((r/'images').glob('*'))),'log_tail':tail}
@app.get('/api/projects/{i}/analysis')
def analyse_mesh(i):return analyse(i)
@app.post('/api/projects/{i}/repair')
def repair_mesh(i):
 m=load_mesh(mesh_path(i));m.remove_unreferenced_vertices();m.remove_infinite_values();m.merge_vertices();trimesh.repair.fix_normals(m,multibody=True);trimesh.repair.fill_holes(m);clear_derived(i);m.export(project_dir(i)/'meshes'/'repaired.stl');return {'status':'repaired','watertight':bool(m.is_watertight)}
@app.post('/api/projects/{i}/missing-part/preview')
def missing_part_preview(i,x:MissingPartRequest):
 clear_missing_preview(i)
 try:patch,combined,plane=create_mirrored_repair(load_mesh(source_for_missing_repair(i)),x.axis,x.keep_side,x.overlap_mm)
 except ValueError as e:raise HTTPException(400,str(e))
 r=project_dir(i)/'meshes';patch.export(r/'missing-part-patch.stl');combined.export(r/'missing-part-preview.glb');combined.export(r/'missing-part-candidate.stl');return {'status':'preview','plane_mm':round(plane,3),'patch_faces':int(len(patch.faces)),'message':'Missing-part preview generated. Inspect it before applying.'}
@app.post('/api/projects/{i}/missing-part/selected-preview')
def selected_missing_part_preview(i,x:SelectedRepairRequest):
 clear_missing_preview(i)
 try:patch,combined,plane,donor_faces,removed_faces,boundary_edges,non_manifold_edges,auto_closed=create_selected_mirrored_repair(load_mesh(source_for_missing_repair(i)),x.axis,x.point,x.radius_mm,x.overlap_mm)
 except ValueError as e:raise HTTPException(400,str(e))
 r=project_dir(i)/'meshes';patch.export(r/'missing-part-patch.stl');combined.export(r/'missing-part-preview.glb');combined.export(r/'missing-part-candidate.stl');return {'status':'preview','plane_mm':round(plane,3),'patch_faces':int(len(patch.faces)),'donor_faces':donor_faces,'removed_faces':removed_faces,'boundary_edges':boundary_edges,'non_manifold_edges':non_manifold_edges,'seam_status':('pass' if boundary_edges==0 and non_manifold_edges==0 else 'review'),'auto_closed':auto_closed,'message':'Selected damaged geometry was replaced with mirrored donor geometry. Inspect the repair before applying.'}
@app.get('/api/projects/{i}/missing-part/preview')
def missing_part_preview_file(i):
 p=project_dir(i)/'meshes'/'missing-part-preview.glb'
 if not p.exists():raise HTTPException(404,'Generate a missing-part preview first')
 return FileResponse(p,media_type='model/gltf-binary',filename='missing-part-preview.glb')
@app.post('/api/projects/{i}/missing-part/apply')
def missing_part_apply(i):
 r=project_dir(i)/'meshes';candidate=r/'missing-part-candidate.stl'
 if not candidate.exists():raise HTTPException(404,'Generate and inspect a missing-part preview first')
 combined=load_mesh(candidate);trimesh.repair.fix_normals(combined,multibody=True);trimesh.repair.fill_holes(combined);edge_counts=np.bincount(combined.edges_unique_inverse) if len(combined.edges_unique_inverse) else np.array([],dtype=int);boundary_edges=int(np.count_nonzero(edge_counts==1));non_manifold_edges=int(np.count_nonzero(edge_counts>2));
 if boundary_edges or non_manifold_edges:raise HTTPException(409,f'Repair not applied: preview still has {boundary_edges} boundary and {non_manifold_edges} non-manifold edge(s). Adjust the selection or overlap and preview again.')
 target=r/'missing-part-repair.stl';combined.export(target);clear_derived(i,keep={'missing-part-repair.stl'});extra=r/'missing-part-candidate.stl';extra.unlink(missing_ok=True);return {'status':'applied','watertight':bool(combined.is_watertight),'components':len(combined.split(only_watertight=False)),'message':'Selected-area replacement applied. Run printability analysis before export.'}
@app.post('/api/projects/{i}/scale')
def scale_mesh(i,x:ScaleRequest):
 if x.current_mm<=0 or x.target_mm<=0:raise HTTPException(400,'Measurements must be greater than zero')
 f=x.target_mm/x.current_mm;m=load_mesh(mesh_path(i));m.apply_scale(f);clear_derived(i);m.export(project_dir(i)/'meshes'/'scaled.stl');return {'scale_factor':f}
@app.get('/api/projects/{i}/mesh-preview')
def preview_mesh(i):
 m=load_mesh(mesh_path(i));p=project_dir(i)/'meshes'/'preview.glb';m.export(p);return FileResponse(p,media_type='model/gltf-binary',filename='preview.glb')
@app.get('/api/projects/{i}/export/stl')
def export_stl(i):
 report=analyse(i)
 if report['printability']['overall']=='fail':raise HTTPException(409,'Export blocked: fix failed printability checks first')
 m=load_mesh(mesh_path(i));r=project_dir(i);name=(r/'name.txt').read_text(encoding='utf-8').strip() or 'Rebuild';safe=''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in name).strip('-_')[:60] or 'Rebuild';filename=f'CCSDESIGN-{safe}.stl';t=r/'exports'/filename;m.export(t);return FileResponse(t,media_type='model/stl',filename=filename)


# Production UI: after `npm run build`, FastAPI serves the React application itself.
FRONTEND_DIST=BUNDLE_ROOT/'frontend'/'dist'
if FRONTEND_DIST.exists():
 app.mount('/',StaticFiles(directory=FRONTEND_DIST,html=True),name='frontend')
