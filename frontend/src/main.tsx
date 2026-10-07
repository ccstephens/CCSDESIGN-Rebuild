import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const API = 'http://127.0.0.1:8000/api'

type Analysis = {
  vertices: number
  faces: number
  watertight: boolean
  winding_consistent: boolean
  volume: number | null
  bounds_mm: number[]
}

function App() {
  const [projectId, setProjectId] = useState('')
  const [name, setName] = useState('My Rebuild')
  const [status, setStatus] = useState('Create a project to begin.')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')

  async function createProject() {
    const res = await fetch(`${API}/projects`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name}) })
    const data = await res.json()
    setProjectId(data.id)
    setStatus(`Project ${data.name} created. Add 20–50 photos, or load a mesh for repair/testing.`)
  }

  async function uploadImages(files: FileList | null) {
    if (!projectId || !files?.length) return
    const form = new FormData()
    Array.from(files).forEach(file => form.append('files', file))
    const res = await fetch(`${API}/projects/${projectId}/images`, {method:'POST', body:form})
    const data = await res.json()
    setStatus(res.ok ? `${data.total} photos loaded.` : data.detail)
  }

  async function uploadMesh(file?: File) {
    if (!projectId || !file) return
    const form = new FormData(); form.append('file', file)
    const res = await fetch(`${API}/projects/${projectId}/mesh`, {method:'POST', body:form})
    const data = await res.json()
    setStatus(res.ok ? 'Mesh loaded. Run Analyze or Repair.' : data.detail)
  }

  async function action(path: string, options: RequestInit = {}) {
    if (!projectId) return
    const res = await fetch(`${API}/projects/${projectId}/${path}`, {method:'POST', ...options})
    const data = await res.json()
    setStatus(res.ok ? JSON.stringify(data) : data.detail)
    await analyse()
  }

  async function analyse() {
    if (!projectId) return
    const res = await fetch(`${API}/projects/${projectId}/analysis`)
    if (!res.ok) return
    setAnalysis(await res.json())
    setPreviewUrl(`${API}/projects/${projectId}/mesh-preview?ts=${Date.now()}`)
  }

  useEffect(() => { setAnalysis(null); setPreviewUrl('') }, [projectId])

  return <main>
    <header><div><span className="brand">CCSDESIGN</span><strong> Rebuild</strong></div><span className="version">V1</span></header>
    <section className="hero">
      <p className="eyebrow">PHOTO → 3D → REPAIR → STL</p>
      <h1>Rebuild real objects for 3D printing.</h1>
      <p>Capture a complete or damaged object, reconstruct the geometry, set real-world scale, repair the mesh and export a printable STL.</p>
    </section>
    <section className="workspace">
      <aside>
        <h2>1. Project</h2>
        <input value={name} onChange={e=>setName(e.target.value)} placeholder="Project name" />
        <button onClick={createProject}>New project</button>
        <h2>2. Capture</h2>
        <label className="drop">Add 20–50 photos<input hidden multiple type="file" accept="image/*" onChange={e=>uploadImages(e.target.files)} /></label>
        <button disabled={!projectId} onClick={()=>action('reconstruct')}>Build 3D scan</button>
        <label className="secondary">Or load mesh<input hidden type="file" accept=".stl,.obj,.ply,.glb,.gltf" onChange={e=>uploadMesh(e.target.files?.[0])}/></label>
        <h2>3. Repair</h2>
        <button disabled={!projectId} onClick={analyse}>Analyze mesh</button>
        <button disabled={!projectId} onClick={()=>action('repair')}>Auto repair</button>
        <h2>4. Scale</h2>
        <Scale projectId={projectId} onDone={analyse} setStatus={setStatus}/>
        <h2>5. Export</h2>
        <a className={!projectId ? 'disabled export' : 'export'} href={projectId ? `${API}/projects/${projectId}/export/stl` : undefined}>Export STL</a>
      </aside>
      <article>
        <div className="viewer">
          {previewUrl ? <model-viewer-placeholder url={previewUrl}/> : <div className="empty"><b>3D workspace</b><span>Your reconstructed or imported model will appear here.</span></div>}
        </div>
        <div className="status">{status}</div>
        {analysis && <div className="metrics">
          <Metric label="Vertices" value={analysis.vertices.toLocaleString()}/><Metric label="Faces" value={analysis.faces.toLocaleString()}/>
          <Metric label="Watertight" value={analysis.watertight?'YES':'NO'}/><Metric label="Normals" value={analysis.winding_consistent?'OK':'CHECK'}/>
          <Metric label="Size mm" value={analysis.bounds_mm.join(' × ')}/>
        </div>}
      </article>
    </section>
  </main>
}

function Scale({projectId,onDone,setStatus}:{projectId:string,onDone:()=>void,setStatus:(s:string)=>void}) {
  const [current,setCurrent]=useState('100'); const [target,setTarget]=useState('100')
  async function apply(){
    const res=await fetch(`${API}/projects/${projectId}/scale`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_mm:Number(current),target_mm:Number(target)})})
    const data=await res.json(); setStatus(res.ok?`Scaled by ${data.scale_factor.toFixed(4)}×`:data.detail); if(res.ok) onDone()
  }
  return <div className="scale"><input value={current} onChange={e=>setCurrent(e.target.value)} title="Measured on model"/><span>→</span><input value={target} onChange={e=>setTarget(e.target.value)} title="Real measurement"/><button disabled={!projectId} onClick={apply}>Set mm</button></div>
}
function Metric({label,value}:{label:string,value:string}){return <div><small>{label}</small><b>{value}</b></div>}

// Lightweight GLB preview without adding UI complexity to V1.
function ModelViewerPlaceholder({url}:{url:string}) { return <div className="empty"><b>Mesh ready</b><span>Preview generated: {url.split('?')[0].split('/').pop()}</span><span>Interactive Three.js viewer is the next V1 build step.</span></div> }

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)
