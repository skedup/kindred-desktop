import {
  validateFrameManifest,
  type FrameManifestV1,
  type VisualAssetDescriptorV1,
  type VisualRendererV1,
} from './visualPack'

export type VisualLayerRole = 'body' | 'decoration'

export interface VisualResourceLoader {
  loadImage(source: string, signal: AbortSignal): Promise<string>
  loadFrameManifest(source: string, signal: AbortSignal): Promise<unknown>
}

export interface VisualLayer {
  setImage(url: string): void
  setOpacity(opacity: number, durationMs: number): void
  dispose(): void
}

export interface VisualSurface {
  createLayer(role: VisualLayerRole): VisualLayer
}

export interface AnimationFrameClock {
  now(): number
  request(callback: (timestamp: number) => void, delayMs: number): number
  cancel(handle: number): void
}

export interface RendererAdapter {
  readonly renderer: VisualRendererV1
  load(signal: AbortSignal): Promise<void>
  enter(): void
  setSuspended(suspended: boolean): void
  setOpacity(opacity: number, durationMs: number): void
  dispose(): void
}

export interface RendererAdapterFactory {
  readonly availableRenderers: ReadonlySet<VisualRendererV1>
  create(descriptor: VisualAssetDescriptorV1, role: VisualLayerRole): RendererAdapter
}

export interface RendererMotionPlan {
  readonly motionKey: string
  readonly motionInstanceId: string
  readonly reducedMotion: boolean
  readonly body: VisualAssetDescriptorV1
  readonly decoration?: VisualAssetDescriptorV1
}

export interface PreparedRendererMotion {
  readonly rendererNames: readonly VisualRendererV1[]
}

export interface RendererTransition {
  readonly durationMs: number
}

export interface RendererTransitionClock {
  setTimeout(callback: () => void, delayMs: number): unknown
  clearTimeout(handle: unknown): void
}

export interface RendererSession {
  prepare(plan: RendererMotionPlan, signal: AbortSignal): Promise<PreparedRendererMotion>
  activate(motion: PreparedRendererMotion, transition: RendererTransition): void
  discard(motion: PreparedRendererMotion): void
  suspend(): void
  resume(): void
  dispose(): void
}

export interface RendererSessionOptions {
  readonly transitionClock?: RendererTransitionClock
}

export interface RendererSessionFactory {
  readonly availableRenderers: ReadonlySet<VisualRendererV1>
  /**
   * Creates only the lightweight session owner. Implementations must not perform
   * renderer I/O or throw here; all fallible backend initialization belongs in
   * RendererSession.prepare() so the stage can apply its normal fallback path.
   */
  create(options?: RendererSessionOptions): RendererSession
}

const DEFAULT_ANIMATION_CLOCK: AnimationFrameClock = {
  now: () => performance.now(),
  request: (callback, delayMs) =>
    window.setTimeout(() => callback(performance.now()), delayMs),
  cancel: (handle) => window.clearTimeout(handle),
}

const DEFAULT_TRANSITION_CLOCK: RendererTransitionClock = {
  setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted', 'AbortError')
}

export class BrowserVisualResourceLoader implements VisualResourceLoader {
  constructor(
    private readonly resolveSource: (source: string) => string,
    private readonly resolveFrameManifestValue?: (source: string) => unknown,
    private readonly fetchValue: typeof fetch = globalThis.fetch,
    private readonly createImage: () => HTMLImageElement = () => new Image(),
  ) {}

  loadImage(source: string, signal: AbortSignal): Promise<string> {
    if (signal.aborted) return Promise.reject(abortError())
    const url = this.resolveSource(source)
    return new Promise((resolve, reject) => {
      const image = this.createImage()
      const cleanup = () => {
        image.onload = null
        image.onerror = null
        signal.removeEventListener('abort', onAbort)
      }
      const onAbort = () => {
        cleanup()
        image.src = ''
        reject(abortError())
      }
      image.onload = () => {
        cleanup()
        resolve(url)
      }
      image.onerror = () => {
        cleanup()
        reject(new Error('VisualImageLoadError'))
      }
      signal.addEventListener('abort', onAbort, { once: true })
      image.src = url
    })
  }

  async loadFrameManifest(source: string, signal: AbortSignal): Promise<unknown> {
    if (signal.aborted) throw abortError()
    if (this.resolveFrameManifestValue !== undefined) {
      return this.resolveFrameManifestValue(source)
    }
    const response = await this.fetchValue(this.resolveSource(source), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
    })
    if (!response.ok) throw new Error('VisualFrameManifestLoadError')
    return response.json()
  }
}

class DomVisualLayer implements VisualLayer {
  private disposed = false

  constructor(private readonly element: HTMLImageElement) {}

  setImage(url: string): void {
    if (!this.disposed) this.element.src = url
  }

  setOpacity(opacity: number, durationMs: number): void {
    if (this.disposed) return
    this.element.style.transition = durationMs > 0 ? `opacity ${durationMs}ms linear` : 'none'
    if (durationMs > 0) void this.element.offsetWidth
    this.element.style.opacity = String(Math.min(Math.max(opacity, 0), 1))
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.element.remove()
  }
}

export class DomVisualSurface implements VisualSurface {
  constructor(private readonly root: HTMLElement) {}

  createLayer(role: VisualLayerRole): VisualLayer {
    const image = document.createElement('img')
    image.alt = ''
    image.draggable = false
    image.setAttribute('aria-hidden', 'true')
    image.dataset.visualLayer = role
    Object.assign(image.style, {
      position: 'absolute',
      inset: '0',
      width: '100%',
      height: '100%',
      objectFit: 'contain',
      pointerEvents: 'none',
      userSelect: 'none',
    })
    this.root.append(image)
    return new DomVisualLayer(image)
  }
}

abstract class BaseImageAdapter implements RendererAdapter {
  abstract readonly renderer: VisualRendererV1
  protected readonly layer: VisualLayer
  protected disposed = false

  constructor(surface: VisualSurface, role: VisualLayerRole) {
    this.layer = surface.createLayer(role)
  }

  abstract load(signal: AbortSignal): Promise<void>
  abstract enter(): void
  abstract setSuspended(suspended: boolean): void

  setOpacity(opacity: number, durationMs: number): void {
    this.layer.setOpacity(opacity, durationMs)
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.layer.dispose()
  }
}

export class StaticImageAdapter extends BaseImageAdapter {
  readonly renderer = 'static' as const
  private url: string | null = null

  constructor(
    private readonly descriptor: VisualAssetDescriptorV1 & { renderer: 'static' },
    private readonly loader: VisualResourceLoader,
    surface: VisualSurface,
    role: VisualLayerRole,
  ) {
    super(surface, role)
  }

  async load(signal: AbortSignal): Promise<void> {
    const url = await this.loader.loadImage(this.descriptor.source, signal)
    if (this.disposed || signal.aborted) throw abortError()
    this.url = url
  }

  enter(): void {
    if (this.url === null || this.disposed) throw new Error('StaticImageAdapterNotLoaded')
    this.layer.setImage(this.url)
  }

  setSuspended(_suspended: boolean): void {}
}

export class FrameAnimationAdapter extends BaseImageAdapter {
  readonly renderer = 'frames' as const
  private manifest: FrameManifestV1 | null = null
  private frames: readonly string[] = []
  private urls = new Map<string, string>()
  private position = 0
  private entered = false
  private suspended = false
  private frameHandle: number | null = null
  private lastFrameAt = 0

  constructor(
    private readonly descriptor: VisualAssetDescriptorV1 & { renderer: 'frames' },
    private readonly loader: VisualResourceLoader,
    surface: VisualSurface,
    role: VisualLayerRole,
    private readonly clock: AnimationFrameClock = DEFAULT_ANIMATION_CLOCK,
  ) {
    super(surface, role)
  }

  async load(signal: AbortSignal): Promise<void> {
    const manifest = validateFrameManifest(
      await this.loader.loadFrameManifest(this.descriptor.source, signal),
    )
    const frames = [...manifest.enter, ...manifest.loop]
    const loaded = await Promise.all(
      [...new Set(frames)].map(
        async (source) => [source, await this.loader.loadImage(source, signal)] as const,
      ),
    )
    if (this.disposed || signal.aborted) throw abortError()
    this.manifest = manifest
    this.frames = frames
    this.urls = new Map(loaded)
  }

  enter(): void {
    if (this.manifest === null || this.frames.length === 0 || this.disposed) {
      throw new Error('FrameAnimationAdapterNotLoaded')
    }
    this.cancelFrame()
    this.position = 0
    this.entered = true
    this.showCurrentFrame()
    this.lastFrameAt = this.clock.now()
    if (!this.suspended) this.scheduleFrame()
  }

  setSuspended(suspended: boolean): void {
    if (this.suspended === suspended || this.disposed) return
    this.suspended = suspended
    if (suspended) {
      this.cancelFrame()
    } else if (this.entered) {
      this.lastFrameAt = this.clock.now()
      this.scheduleFrame()
    }
  }

  override dispose(): void {
    this.cancelFrame()
    super.dispose()
  }

  private scheduleFrame(): void {
    if (this.frameHandle !== null || this.suspended || this.disposed) return
    const manifest = this.manifest
    if (manifest === null) return
    const duration = 1000 / manifest.fps
    const elapsed = Math.max(0, this.clock.now() - this.lastFrameAt)
    const delay = Math.max(0, duration - elapsed)
    this.frameHandle = this.clock.request(
      (timestamp) => {
        this.frameHandle = null
        this.advance(timestamp)
      },
      delay,
    )
  }

  private advance(timestamp: number): void {
    const manifest = this.manifest
    if (manifest === null || this.suspended || this.disposed) return
    const duration = 1000 / manifest.fps
    const elapsed = Math.max(0, timestamp - this.lastFrameAt)
    const steps = Math.floor(elapsed / duration)
    if (steps > 0) {
      this.position += steps
      this.lastFrameAt += steps * duration
      this.showCurrentFrame()
    }
    this.scheduleFrame()
  }

  private showCurrentFrame(): void {
    const manifest = this.manifest
    if (manifest === null) return
    let source: string
    if (this.position < manifest.enter.length) source = manifest.enter[this.position]
    else source = manifest.loop[(this.position - manifest.enter.length) % manifest.loop.length]
    const url = this.urls.get(source)
    if (url === undefined) throw new Error('FrameAnimationResourceMissing')
    this.layer.setImage(url)
  }

  private cancelFrame(): void {
    if (this.frameHandle === null) return
    this.clock.cancel(this.frameHandle)
    this.frameHandle = null
  }
}

export class DefaultRendererAdapterFactory implements RendererAdapterFactory {
  readonly availableRenderers = new Set<VisualRendererV1>(['static', 'frames'])

  constructor(
    private readonly loader: VisualResourceLoader,
    private readonly surface: VisualSurface,
    private readonly clock: AnimationFrameClock = DEFAULT_ANIMATION_CLOCK,
  ) {}

  create(descriptor: VisualAssetDescriptorV1, role: VisualLayerRole): RendererAdapter {
    if (descriptor.renderer === 'static') {
      return new StaticImageAdapter(
        { renderer: 'static', source: descriptor.source },
        this.loader,
        this.surface,
        role,
      )
    }
    return new FrameAnimationAdapter(
      { renderer: 'frames', source: descriptor.source },
      this.loader,
      this.surface,
      role,
      this.clock,
    )
  }
}

interface AdapterMotion extends PreparedRendererMotion {
  readonly plan: RendererMotionPlan
  readonly adapters: RendererAdapter[]
  readonly loadController: AbortController
  detachCallerAbort(): void
}

class DefaultRendererSession implements RendererSession {
  private readonly owned = new Set<AdapterMotion>()
  private current: AdapterMotion | null = null
  private retiring: AdapterMotion | null = null
  private retirementTimer: unknown | undefined
  private suspended = false
  private disposed = false

  constructor(
    private readonly adapters: RendererAdapterFactory,
    private readonly transitionClock: RendererTransitionClock,
  ) {}

  async prepare(plan: RendererMotionPlan, signal: AbortSignal): Promise<PreparedRendererMotion> {
    if (this.disposed || signal.aborted) throw abortError()
    const adapters: RendererAdapter[] = []
    try {
      adapters.push(this.adapters.create(plan.body, 'body'))
      if (plan.decoration !== undefined) {
        adapters.push(this.adapters.create(plan.decoration, 'decoration'))
      }
    } catch (error) {
      adapters.forEach((adapter) => adapter.dispose())
      throw error
    }
    const loadController = new AbortController()
    const abortFromCaller = () => loadController.abort()
    signal.addEventListener('abort', abortFromCaller, { once: true })
    if (signal.aborted) loadController.abort()
    const motion: AdapterMotion = {
      plan,
      adapters,
      rendererNames: adapters.map((adapter) => adapter.renderer),
      loadController,
      detachCallerAbort: () => signal.removeEventListener('abort', abortFromCaller),
    }
    this.owned.add(motion)
    try {
      adapters.forEach((adapter) => adapter.setOpacity(0, 0))
      await Promise.all(adapters.map((adapter) => adapter.load(loadController.signal)))
      if (this.disposed || signal.aborted) throw abortError()
      motion.detachCallerAbort()
      return motion
    } catch (error) {
      this.release(motion)
      throw error
    }
  }

  activate(prepared: PreparedRendererMotion, transition: RendererTransition): void {
    const motion = this.requireOwned(prepared)
    if (motion === this.current || motion === this.retiring) {
      throw new Error('RendererMotionAlreadyActive')
    }
    this.cancelRetirement()
    const previous = this.current
    try {
      motion.adapters.forEach((adapter) => adapter.enter())
      motion.adapters.forEach((adapter) => adapter.setSuspended(this.suspended))
      const durationMs = previous === null ? 0 : Math.max(0, Math.floor(transition.durationMs))
      motion.adapters.forEach((adapter) => adapter.setOpacity(1, durationMs))
      previous?.adapters.forEach((adapter) => adapter.setOpacity(0, durationMs))
      this.current = motion
      if (previous === null) return
      if (durationMs === 0) {
        this.release(previous)
        return
      }
      this.retiring = previous
      this.retirementTimer = this.transitionClock.setTimeout(() => {
        this.release(this.retiring)
        this.retiring = null
        this.retirementTimer = undefined
      }, durationMs)
    } catch (error) {
      previous?.adapters.forEach((adapter) => {
        try {
          adapter.setOpacity(1, 0)
        } catch {
          // Best-effort rollback keeps the previous motion owned until explicit disposal.
        }
      })
      this.current = previous
      this.release(motion)
      throw error
    }
  }

  discard(prepared: PreparedRendererMotion): void {
    const motion = prepared as AdapterMotion
    if (!this.owned.has(motion)) return
    if (motion === this.current || motion === this.retiring) return
    this.release(motion)
  }

  suspend(): void {
    this.setSuspended(true)
  }

  resume(): void {
    this.setSuspended(false)
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.cancelRetirement()
    for (const motion of [...this.owned]) this.release(motion)
    this.current = null
  }

  private requireOwned(prepared: PreparedRendererMotion): AdapterMotion {
    const motion = prepared as AdapterMotion
    if (this.disposed || !this.owned.has(motion)) throw new Error('RendererMotionNotOwned')
    return motion
  }

  private setSuspended(suspended: boolean): void {
    if (this.disposed || this.suspended === suspended) return
    this.suspended = suspended
    for (const motion of [this.current, this.retiring]) {
      motion?.adapters.forEach((adapter) => adapter.setSuspended(suspended))
    }
  }

  private cancelRetirement(): void {
    if (this.retirementTimer !== undefined) {
      this.transitionClock.clearTimeout(this.retirementTimer)
      this.retirementTimer = undefined
    }
    this.release(this.retiring)
    this.retiring = null
  }

  private release(motion: AdapterMotion | null): void {
    if (motion === null || !this.owned.delete(motion)) return
    motion.detachCallerAbort()
    motion.loadController.abort()
    motion.adapters.forEach((adapter) => adapter.dispose())
    if (this.current === motion) this.current = null
    if (this.retiring === motion) this.retiring = null
  }
}

export class DefaultRendererSessionFactory implements RendererSessionFactory {
  readonly availableRenderers: ReadonlySet<VisualRendererV1>

  constructor(private readonly adapters: RendererAdapterFactory) {
    this.availableRenderers = adapters.availableRenderers
  }

  create(options: RendererSessionOptions = {}): RendererSession {
    return new DefaultRendererSession(
      this.adapters,
      options.transitionClock ?? DEFAULT_TRANSITION_CLOCK,
    )
  }
}
