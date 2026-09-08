import { useEffect, useRef, useState } from 'react'

type ViewerProps = {
  active: boolean
  imageUrl: string | null
  modelUrl: string | null
  title: string
}

export function Idea3DViewer({ active, imageUrl, modelUrl, title }: ViewerProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setReady(false)
    setFailed(false)
    if (!active || !hostRef.current || !modelUrl) return

    const host = hostRef.current
    let disposed = false
    let cleanup = () => {}

    void Promise.all([
      import('three'),
      import('three/examples/jsm/controls/OrbitControls.js'),
      import('three/examples/jsm/loaders/GLTFLoader.js'),
      import('three/examples/jsm/environments/RoomEnvironment.js'),
    ]).then(async ([THREE, controlsModule, loaderModule, environmentModule]) => {
      if (disposed) return
      const { OrbitControls } = controlsModule
      const { GLTFLoader } = loaderModule
      const { RoomEnvironment } = environmentModule

      const scene = new THREE.Scene()
      const renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: 'high-performance',
      })
      renderer.setClearColor(0x000000, 0)
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
      renderer.outputColorSpace = THREE.SRGBColorSpace
      renderer.toneMapping = THREE.ACESFilmicToneMapping
      renderer.toneMappingExposure = 1.08
      renderer.shadowMap.enabled = true
      renderer.shadowMap.type = THREE.PCFSoftShadowMap
      renderer.domElement.setAttribute('aria-label', `Точная 3D-модель: ${title}`)
      host.replaceChildren(renderer.domElement)

      const camera = new THREE.PerspectiveCamera(31, 1, 0.01, 200)
      const controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = true
      controls.dampingFactor = 0.065
      controls.enablePan = false
      controls.enableZoom = false
      controls.minPolarAngle = Math.PI * 0.16
      controls.maxPolarAngle = Math.PI * 0.49
      controls.autoRotate = true
      controls.autoRotateSpeed = 0.42

      const pmrem = new THREE.PMREMGenerator(renderer)
      const room = new RoomEnvironment()
      const environment = pmrem.fromScene(room, 0.035).texture
      scene.environment = environment
      room.dispose()
      pmrem.dispose()

      const hemisphere = new THREE.HemisphereLight(0xfff8ed, 0x697174, 1.8)
      scene.add(hemisphere)
      const key = new THREE.DirectionalLight(0xfff0d8, 4.2)
      key.position.set(6.5, 9, 7)
      key.castShadow = true
      key.shadow.mapSize.set(2048, 2048)
      key.shadow.bias = -0.0002
      key.shadow.normalBias = 0.025
      scene.add(key)
      const fill = new THREE.DirectionalLight(0xdde8f4, 1.35)
      fill.position.set(-6, 4.5, -4)
      scene.add(fill)
      const rim = new THREE.DirectionalLight(0xffdfbd, 1.15)
      rim.position.set(-2, 6, 7)
      scene.add(rim)

      const root = new THREE.Group()
      scene.add(root)

      let modelRoot: InstanceType<typeof THREE.Object3D> | null = null
      let floor: InstanceType<typeof THREE.Mesh> | null = null
      let halo: InstanceType<typeof THREE.Mesh> | null = null
      let resizeObserver: ResizeObserver | null = null
      let animationFrame = 0

      const onInteract = () => {
        controls.autoRotate = false
        host.dataset.interacted = 'true'
      }
      renderer.domElement.addEventListener('pointerdown', onInteract, { passive: true })
      renderer.domElement.addEventListener('wheel', onInteract, { passive: true })

      const disposeModel = () => {
        if (!modelRoot) return
        modelRoot.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return
          object.geometry?.dispose()
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          materials.forEach((material) => {
            const candidate = material as InstanceType<typeof THREE.Material> & Record<string, unknown>
            for (const value of Object.values(candidate)) {
              if (value instanceof THREE.Texture) value.dispose()
            }
            material.dispose()
          })
        })
      }

      cleanup = () => {
        window.cancelAnimationFrame(animationFrame)
        resizeObserver?.disconnect()
        controls.dispose()
        renderer.domElement.removeEventListener('pointerdown', onInteract)
        renderer.domElement.removeEventListener('wheel', onInteract)
        disposeModel()
        floor?.geometry.dispose()
        if (floor) (floor.material as InstanceType<typeof THREE.Material>).dispose()
        halo?.geometry.dispose()
        if (halo) (halo.material as InstanceType<typeof THREE.Material>).dispose()
        environment.dispose()
        renderer.dispose()
        renderer.forceContextLoss()
        host.replaceChildren()
      }

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
      resizeObserver = new ResizeObserver(resize)
      resizeObserver.observe(host)
      resize()
      render()

      const gltf = await new GLTFLoader().loadAsync(modelUrl)
      if (disposed) {
        modelRoot = gltf.scene
        cleanup()
        return
      }
      modelRoot = gltf.scene
      if (!modelRoot.children.length) throw new Error('GLB scene is empty')

      modelRoot.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return
        object.castShadow = true
        object.receiveShadow = true
        const materials = Array.isArray(object.material) ? object.material : [object.material]
        materials.forEach((material) => {
          if (material instanceof THREE.MeshStandardMaterial || material instanceof THREE.MeshPhysicalMaterial) {
            material.envMapIntensity = 0.8
            material.needsUpdate = true
          }
        })
      })
      root.add(modelRoot)

      const rawBox = new THREE.Box3().setFromObject(modelRoot)
      if (rawBox.isEmpty()) throw new Error('GLB has no renderable bounds')
      const rawSize = rawBox.getSize(new THREE.Vector3())
      const longest = Math.max(rawSize.x, rawSize.y, rawSize.z)
      if (!Number.isFinite(longest) || longest <= 0) throw new Error('GLB bounds are invalid')

      const scale = 4.9 / longest
      modelRoot.scale.setScalar(scale)
      modelRoot.updateMatrixWorld(true)
      const scaledBox = new THREE.Box3().setFromObject(modelRoot)
      const center = scaledBox.getCenter(new THREE.Vector3())
      modelRoot.position.x -= center.x
      modelRoot.position.z -= center.z
      modelRoot.position.y -= scaledBox.min.y
      modelRoot.updateMatrixWorld(true)

      // Fit in model-local/world-aligned space first, then apply the presentation angle.
      // This keeps the imported mesh centered even for long/asymmetric buildings.
      root.rotation.y = -0.5
      root.updateMatrixWorld(true)

      const fittedBox = new THREE.Box3().setFromObject(modelRoot)
      const fittedSize = fittedBox.getSize(new THREE.Vector3())
      const horizontal = Math.max(fittedSize.x, fittedSize.z)
      const modelHeight = Math.max(fittedSize.y, 0.5)
      const targetY = modelHeight * 0.43

      const floorGeometry = new THREE.PlaneGeometry(horizontal * 2.05, horizontal * 1.72)
      const floorMaterial = new THREE.ShadowMaterial({ color: 0x685f54, opacity: 0.18 })
      floor = new THREE.Mesh(floorGeometry, floorMaterial)
      floor.rotation.x = -Math.PI / 2
      floor.position.y = -0.018
      floor.receiveShadow = true
      scene.add(floor)

      const haloGeometry = new THREE.CircleGeometry(horizontal * 0.82, 96)
      const haloMaterial = new THREE.MeshBasicMaterial({
        color: 0x9d8f7c,
        transparent: true,
        opacity: 0.075,
        depthWrite: false,
      })
      halo = new THREE.Mesh(haloGeometry, haloMaterial)
      halo.rotation.x = -Math.PI / 2
      halo.scale.y = 0.72
      halo.position.y = -0.028
      scene.add(halo)

      const viewSpan = Math.max(horizontal, modelHeight * 0.92)
      const fovRadians = THREE.MathUtils.degToRad(camera.fov)
      const distance = (viewSpan / (2 * Math.tan(fovRadians / 2))) * 1.34
      camera.position.set(distance * 0.78, targetY + distance * 0.24, distance * 0.92)
      camera.near = Math.max(distance / 1000, 0.01)
      camera.far = distance * 12
      camera.updateProjectionMatrix()
      controls.target.set(0, targetY, 0)
      controls.minDistance = distance * 0.82
      controls.maxDistance = distance * 1.18
      controls.update()

      const shadowSpan = horizontal * 1.35
      key.shadow.camera.left = -shadowSpan
      key.shadow.camera.right = shadowSpan
      key.shadow.camera.top = shadowSpan
      key.shadow.camera.bottom = -shadowSpan
      key.shadow.camera.near = 0.5
      key.shadow.camera.far = 30
      key.shadow.camera.updateProjectionMatrix()

      setReady(true)
    }).catch(() => {
      if (!disposed) {
        cleanup()
        setFailed(true)
      }
    })

    return () => {
      disposed = true
      cleanup()
    }
  }, [active, modelUrl, title])

  const hasModel = Boolean(modelUrl)
  return (
    <div className={`idea-3d-viewer ${ready ? 'is-ready' : ''} ${failed ? 'is-fallback' : ''} ${hasModel ? 'has-model' : 'poster-only'}`}>
      {imageUrl ? <img className="idea-3d-poster" src={imageUrl} alt={title} loading={active ? 'eager' : 'lazy'} /> : !hasModel ? <div className="idea-3d-empty">Добавьте визуализацию или GLB в веб-админке</div> : null}
      {active && hasModel && !failed && <div className="idea-3d-canvas" ref={hostRef} />}
      {active && hasModel && !ready && !failed && <div className="idea-3d-loading">Загружаем точную 3D-модель…</div>}
      {active && hasModel && failed && <div className="idea-3d-loading">3D временно недоступно · показываем визуализацию</div>}
    </div>
  )
}
