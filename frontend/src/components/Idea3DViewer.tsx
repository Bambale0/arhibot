import { useEffect, useMemo, useRef, useState } from 'react'
import type { ArchitecturePackage } from '../types'

type ViewerProps = {
  active: boolean
  imageUrl: string | null
  textureUrls: string[]
  architecture: ArchitecturePackage | null
  title: string
}

type ModelDimensions = {
  width: number
  depth: number
  height: number
  levels: { z: number; height: number; width: number; depth: number }[]
  roofType: 'gable' | 'hip' | 'flat'
  roofRise: number
}

function bounds(points: { x: number; y: number }[]) {
  if (!points.length) return { width: 1, depth: 1 }
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  return {
    width: Math.max(Math.max(...xs) - Math.min(...xs), 0.5),
    depth: Math.max(Math.max(...ys) - Math.min(...ys), 0.5),
  }
}

function modelDimensions(architecture: ArchitecturePackage | null): ModelDimensions {
  const sourceLevels = architecture?.geometry.levels || []
  if (!sourceLevels.length) {
    return {
      width: 3.8,
      depth: 2.7,
      height: 2.5,
      levels: [{ z: 0, height: 2.5, width: 3.8, depth: 2.7 }],
      roofType: 'gable',
      roofRise: 1.15,
    }
  }

  const rawLevels = sourceLevels.map((level) => {
    const size = bounds(level.footprint.points)
    return { z: level.z, height: level.height, width: size.width, depth: size.depth }
  })
  const minZ = Math.min(...rawLevels.map((level) => level.z))
  const maxZ = Math.max(...rawLevels.map((level) => level.z + level.height))
  const rawWidth = Math.max(...rawLevels.map((level) => level.width))
  const rawDepth = Math.max(...rawLevels.map((level) => level.depth))
  const rawHeight = Math.max(maxZ - minZ, 0.5)
  const scale = 4.2 / Math.max(rawWidth, rawDepth, rawHeight)
  const roof = architecture?.geometry.roof
  const roofRiseRaw = roof && roof.type !== 'flat' ? Math.max(roof.ridge_z - roof.eave_z, rawWidth * 0.18) : 0.18

  return {
    width: rawWidth * scale,
    depth: rawDepth * scale,
    height: rawHeight * scale,
    levels: rawLevels.map((level) => ({
      z: (level.z - minZ) * scale,
      height: level.height * scale,
      width: level.width * scale,
      depth: level.depth * scale,
    })),
    roofType: roof?.type || 'gable',
    roofRise: roofRiseRaw * scale,
  }
}

function uniqueUrls(primary: string | null, urls: string[]) {
  const values = [primary, ...urls].filter((value): value is string => Boolean(value))
  return values.filter((value, index) => values.indexOf(value) === index).slice(0, 4)
}

export function Idea3DViewer({ active, imageUrl, textureUrls, architecture, title }: ViewerProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  const urls = useMemo(() => uniqueUrls(imageUrl, textureUrls), [imageUrl, textureUrls])

  useEffect(() => {
    setReady(false)
    setFailed(false)
    if (!active || !hostRef.current || !urls.length) return

    const host = hostRef.current
    let disposed = false
    let cleanup = () => {}

    Promise.all([
      import('three'),
      import('three/examples/jsm/controls/OrbitControls.js'),
    ]).then(([THREE, controlsModule]) => {
      if (disposed) return
      const { OrbitControls } = controlsModule
      const scene = new THREE.Scene()
      const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
      renderer.outputColorSpace = THREE.SRGBColorSpace
      renderer.toneMapping = THREE.ACESFilmicToneMapping
      renderer.toneMappingExposure = 1.05
      renderer.shadowMap.enabled = true
      renderer.shadowMap.type = THREE.PCFSoftShadowMap
      renderer.domElement.setAttribute('aria-label', `3D-обзор: ${title}`)
      host.replaceChildren(renderer.domElement)

      const dimensions = modelDimensions(architecture)
      const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100)
      const cameraDistance = Math.max(dimensions.width, dimensions.depth, dimensions.height + dimensions.roofRise) * 2.15
      camera.position.set(cameraDistance * 0.72, cameraDistance * 0.48, cameraDistance)

      const controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = true
      controls.dampingFactor = 0.075
      controls.enablePan = false
      controls.enableZoom = false
      controls.minPolarAngle = Math.PI * 0.18
      controls.maxPolarAngle = Math.PI * 0.48
      controls.target.set(0, dimensions.height * 0.48, 0)

      const group = new THREE.Group()
      group.rotation.y = -0.42
      scene.add(group)

      scene.add(new THREE.HemisphereLight(0xfff8e9, 0x5a5f61, 2.0))
      const key = new THREE.DirectionalLight(0xfff2dc, 3.0)
      key.position.set(5, 8, 6)
      key.castShadow = true
      key.shadow.mapSize.set(1024, 1024)
      scene.add(key)
      const fill = new THREE.DirectionalLight(0xdde8ff, 1.35)
      fill.position.set(-5, 4, -3)
      scene.add(fill)

      const textureLoader = new THREE.TextureLoader()
      textureLoader.setCrossOrigin('anonymous')
      const textures = urls.map((url) => {
        const texture = textureLoader.load(url)
        texture.colorSpace = THREE.SRGBColorSpace
        texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 8)
        return texture
      })

      const faceMaterial = (textureIndex: number, roughness = 0.72) => new THREE.MeshStandardMaterial({
        map: textures[textureIndex % textures.length],
        roughness,
        metalness: 0.04,
      })
      const neutral = new THREE.MeshStandardMaterial({ color: 0xd9d2c7, roughness: 0.86, metalness: 0.02 })
      const underside = new THREE.MeshStandardMaterial({ color: 0xb9aa96, roughness: 0.88 })
      const roofMaterial = new THREE.MeshStandardMaterial({ color: 0x343739, roughness: 0.55, metalness: 0.34 })
      const materialsToDispose: InstanceType<typeof THREE.Material>[] = [neutral, underside, roofMaterial]
      const geometriesToDispose: InstanceType<typeof THREE.BufferGeometry>[] = []

      for (const level of dimensions.levels) {
        const geometry = new THREE.BoxGeometry(level.width, level.height, level.depth)
        geometriesToDispose.push(geometry)
        const right = faceMaterial(1)
        const left = faceMaterial(2)
        const top = neutral.clone()
        const bottom = underside.clone()
        const front = faceMaterial(0, 0.66)
        const back = faceMaterial(3)
        materialsToDispose.push(right, left, top, bottom, front, back)
        const mesh = new THREE.Mesh(geometry, [right, left, top, bottom, front, back])
        mesh.position.y = level.z + level.height / 2
        mesh.castShadow = true
        mesh.receiveShadow = true
        group.add(mesh)
      }

      const topY = Math.max(...dimensions.levels.map((level) => level.z + level.height))
      if (dimensions.roofType === 'flat') {
        const geometry = new THREE.BoxGeometry(dimensions.width * 1.06, 0.12, dimensions.depth * 1.08)
        geometriesToDispose.push(geometry)
        const roof = new THREE.Mesh(geometry, roofMaterial)
        roof.position.y = topY + 0.08
        roof.castShadow = true
        group.add(roof)
      } else {
        const rise = Math.max(dimensions.roofRise, dimensions.width * 0.15)
        const halfWidth = dimensions.width / 2
        const slopeLength = Math.sqrt(halfWidth * halfWidth + rise * rise)
        const angle = Math.atan2(rise, halfWidth)
        const roofDepth = dimensions.depth * 1.1
        const slabGeometry = new THREE.BoxGeometry(slopeLength * 1.04, 0.1, roofDepth)
        geometriesToDispose.push(slabGeometry)
        const leftRoof = new THREE.Mesh(slabGeometry, roofMaterial)
        const rightRoof = new THREE.Mesh(slabGeometry, roofMaterial)
        leftRoof.rotation.z = angle
        rightRoof.rotation.z = -angle
        leftRoof.position.set(-dimensions.width * 0.245, topY + rise * 0.52, 0)
        rightRoof.position.set(dimensions.width * 0.245, topY + rise * 0.52, 0)
        leftRoof.castShadow = true
        rightRoof.castShadow = true
        group.add(leftRoof, rightRoof)
      }

      const groundGeometry = new THREE.CircleGeometry(Math.max(dimensions.width, dimensions.depth) * 0.88, 64)
      const groundMaterial = new THREE.MeshBasicMaterial({ color: 0x8b8174, transparent: true, opacity: 0.11, depthWrite: false })
      geometriesToDispose.push(groundGeometry)
      materialsToDispose.push(groundMaterial)
      const ground = new THREE.Mesh(groundGeometry, groundMaterial)
      ground.rotation.x = -Math.PI / 2
      ground.position.y = -0.03
      scene.add(ground)

      const onPointerDown = () => host.dataset.interacted = 'true'
      renderer.domElement.addEventListener('pointerdown', onPointerDown, { passive: true })

      let animationFrame = 0
      const render = () => {
        controls.update()
        renderer.render(scene, camera)
        animationFrame = window.requestAnimationFrame(render)
      }

      const resize = () => {
        const rect = host.getBoundingClientRect()
        if (!rect.width || !rect.height) return
        renderer.setSize(rect.width, rect.height, false)
        camera.aspect = rect.width / rect.height
        camera.updateProjectionMatrix()
      }
      const observer = new ResizeObserver(resize)
      observer.observe(host)
      resize()
      render()
      setReady(true)

      cleanup = () => {
        window.cancelAnimationFrame(animationFrame)
        observer.disconnect()
        controls.dispose()
        renderer.domElement.removeEventListener('pointerdown', onPointerDown)
        geometriesToDispose.forEach((geometry) => geometry.dispose())
        materialsToDispose.forEach((material) => material.dispose())
        textures.forEach((texture) => texture.dispose())
        renderer.dispose()
        renderer.forceContextLoss()
        host.replaceChildren()
      }
    }).catch(() => {
      if (!disposed) setFailed(true)
    })

    return () => {
      disposed = true
      cleanup()
    }
  }, [active, architecture, title, urls])

  return (
    <div className={`idea-3d-viewer ${ready ? 'is-ready' : ''} ${failed ? 'is-fallback' : ''}`}>
      {imageUrl ? <img className="idea-3d-poster" src={imageUrl} alt={title} loading={active ? 'eager' : 'lazy'} /> : <div className="idea-3d-empty">Добавьте визуализацию в веб-админке</div>}
      {active && urls.length > 0 && !failed && <div className="idea-3d-canvas" ref={hostRef} />}
      {active && !ready && urls.length > 0 && !failed && <div className="idea-3d-loading">Собираем 3D…</div>}
    </div>
  )
}
