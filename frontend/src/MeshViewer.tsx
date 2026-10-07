import { Suspense, useEffect } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { Bounds, Center, Environment, Grid, OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'

function Model({ url, wireframe }: { url: string; wireframe: boolean }) {
  const { scene } = useGLTF(url)
  const cloned = scene.clone(true)

  cloned.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.castShadow = true
      child.receiveShadow = true
      child.material = new THREE.MeshStandardMaterial({
        color: '#bfc7d2',
        roughness: 0.65,
        metalness: 0.05,
        wireframe,
      })
    }
  })

  return <primitive object={cloned} />
}

function Background() {
  const { scene } = useThree()
  useEffect(() => {
    scene.background = new THREE.Color('#0c1016')
  }, [scene])
  return null
}

export default function MeshViewer({ url, wireframe }: { url: string; wireframe: boolean }) {
  return (
    <Canvas shadows camera={{ position: [3, 2.2, 3], fov: 42 }}>
      <Background />
      <ambientLight intensity={0.9} />
      <directionalLight position={[4, 7, 5]} intensity={2.2} castShadow />
      <Suspense fallback={null}>
        <Bounds fit clip observe margin={1.25}>
          <Center>
            <Model url={url} wireframe={wireframe} />
          </Center>
        </Bounds>
        <Environment preset="warehouse" />
      </Suspense>
      <Grid infiniteGrid fadeDistance={14} fadeStrength={3} cellSize={0.25} sectionSize={1} position={[0, -1, 0]} />
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
    </Canvas>
  )
}
