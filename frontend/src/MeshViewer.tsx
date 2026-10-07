import { Suspense, useEffect, useMemo, useState } from 'react'
import { Canvas, ThreeEvent, useThree } from '@react-three/fiber'
import { Bounds, Center, Grid, OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'

export type DamageSelection={point:[number,number,number];radius:number}

function Model({url,wireframe,selection,onSelect}:{url:string;wireframe:boolean;selection?:DamageSelection|null;onSelect?:(p:[number,number,number])=>void}){
 const{scene}=useGLTF(url)
 const cloned=useMemo(()=>scene.clone(true),[scene])
 useEffect(()=>{cloned.traverse(child=>{if(child instanceof THREE.Mesh){child.castShadow=true;child.receiveShadow=true;child.material=new THREE.MeshStandardMaterial({color:'#bfc7d2',roughness:.65,metalness:.05,wireframe})}})},[cloned,wireframe])
 function click(e:ThreeEvent<MouseEvent>){if(!onSelect)return;e.stopPropagation();onSelect([e.point.x,e.point.y,e.point.z])}
 return <group onClick={click}><primitive object={cloned}/>{selection&&<mesh position={selection.point}><sphereGeometry args={[selection.radius,24,16]}/><meshStandardMaterial color="#ff5263" transparent opacity={.42} depthWrite={false}/></mesh>}</group>
}
function Background(){const{scene}=useThree();useEffect(()=>{scene.background=new THREE.Color('#0c1016')},[scene]);return null}
export default function MeshViewer({url,wireframe,selection,onSelect}:{url:string;wireframe:boolean;selection?:DamageSelection|null;onSelect?:(p:[number,number,number])=>void}){
 const[controls,setControls]=useState(true)
 return <Canvas shadows camera={{position:[3,2.2,3],fov:42}} onPointerMissed={()=>setControls(true)}><Background/><ambientLight intensity={1.05}/><hemisphereLight intensity={.8} groundColor="#15191f"/><directionalLight position={[4,7,5]} intensity={2.2} castShadow/><Suspense fallback={null}><Bounds fit clip observe margin={1.25}><Center><Model url={url} wireframe={wireframe} selection={selection} onSelect={onSelect}/></Center></Bounds></Suspense><Grid infiniteGrid fadeDistance={14} fadeStrength={3} cellSize={.25} sectionSize={1} position={[0,-1,0]}/><OrbitControls makeDefault enabled={controls} enableDamping dampingFactor={.08} onStart={()=>setControls(true)}/></Canvas>
}
