// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'
import {
  BrowserVisualResourceLoader,
  DefaultRendererAdapterFactory,
  DefaultRendererSessionFactory,
  DomVisualSurface,
  FrameAnimationAdapter,
  StaticImageAdapter,
  type AnimationFrameClock,
  type RendererTransitionClock,
  type VisualLayer,
  type VisualLayerRole,
  type VisualResourceLoader,
  type VisualSurface,
} from './renderAdapters'

class FakeLayer implements VisualLayer {
  readonly images: string[] = []
  readonly opacities: Array<[number, number]> = []
  disposed = false

  setImage(url: string): void {
    this.images.push(url)
  }

  setOpacity(opacity: number, durationMs: number): void {
    this.opacities.push([opacity, durationMs])
  }

  dispose(): void {
    this.disposed = true
  }
}

class FakeSurface implements VisualSurface {
  readonly layers: Array<{ role: VisualLayerRole; layer: FakeLayer }> = []

  createLayer(role: VisualLayerRole): VisualLayer {
    const layer = new FakeLayer()
    this.layers.push({ role, layer })
    return layer
  }
}

class FakeAnimationClock implements AnimationFrameClock {
  private time = 0
  private nextHandle = 1
  private callbacks = new Map<
    number,
    { callback: (timestamp: number) => void; dueAt: number }
  >()

  now(): number {
    return this.time
  }

  request(callback: (timestamp: number) => void, delayMs: number): number {
    const handle = this.nextHandle++
    this.callbacks.set(handle, { callback, dueAt: this.time + delayMs })
    return handle
  }

  cancel(handle: number): void {
    this.callbacks.delete(handle)
  }

  step(milliseconds: number): void {
    this.time += milliseconds
    const due = [...this.callbacks.entries()].filter(
      ([, scheduled]) => scheduled.dueAt <= this.time,
    )
    due.forEach(([handle]) => this.callbacks.delete(handle))
    due.forEach(([, scheduled]) => scheduled.callback(this.time))
  }

  get pending(): number {
    return this.callbacks.size
  }
}

class FakeTransitionClock implements RendererTransitionClock {
  private nextHandle = 1
  private callbacks = new Map<number, () => void>()

  setTimeout(callback: () => void, _delayMs: number): unknown {
    const handle = this.nextHandle++
    this.callbacks.set(handle, callback)
    return handle
  }

  clearTimeout(handle: unknown): void {
    this.callbacks.delete(handle as number)
  }

  flush(): void {
    const callbacks = [...this.callbacks.values()]
    this.callbacks.clear()
    callbacks.forEach((callback) => callback())
  }
}

function loader(options: { failImage?: string } = {}): VisualResourceLoader {
  return {
    loadImage: vi.fn(async (source: string) => {
      if (source === options.failImage) throw new Error('fixture load failure')
      return `asset://${source}`
    }),
    loadFrameManifest: vi.fn(async () => ({
      schema_version: 1,
      fps: 4,
      enter: ['enter-a.png', 'enter-b.png'],
      loop: ['loop-a.png', 'loop-b.png'],
    })),
  }
}

describe('renderer adapters', () => {
  it('reads bundled frame manifests without a runtime fetch', async () => {
    const manifest = {
      schema_version: 1,
      fps: 6,
      enter: ['enter.png'],
      loop: ['loop.png'],
    }
    const resolveManifest = vi.fn(() => manifest)
    const fetchValue = vi.fn()
    const resources = new BrowserVisualResourceLoader(
      (source) => `asset://${source}`,
      resolveManifest,
      fetchValue as unknown as typeof fetch,
    )

    await expect(
      resources.loadFrameManifest('motions/eat.json', new AbortController().signal),
    ).resolves.toBe(manifest)
    expect(resolveManifest).toHaveBeenCalledWith('motions/eat.json')
    expect(fetchValue).not.toHaveBeenCalled()
  })

  it('loads and displays one static local image without scheduling animation', async () => {
    const surface = new FakeSurface()
    const resources = loader()
    const adapter = new StaticImageAdapter(
      { renderer: 'static', source: 'neutral.png' },
      resources,
      surface,
      'body',
    )

    await adapter.load(new AbortController().signal)
    adapter.setOpacity(0, 0)
    adapter.enter()
    adapter.setOpacity(1, 120)

    expect(resources.loadImage).toHaveBeenCalledWith('neutral.png', expect.any(AbortSignal))
    expect(surface.layers[0]?.role).toBe('body')
    expect(surface.layers[0]?.layer.images).toEqual(['asset://neutral.png'])
    expect(surface.layers[0]?.layer.opacities).toEqual([
      [0, 0],
      [1, 120],
    ])
    adapter.dispose()
    expect(surface.layers[0]?.layer.disposed).toBe(true)
  })

  it('plays enter once, loops at manifest FPS, suspends, resumes, and disposes', async () => {
    const surface = new FakeSurface()
    const resources = loader()
    const clock = new FakeAnimationClock()
    const adapter = new FrameAnimationAdapter(
      { renderer: 'frames', source: 'motion.json' },
      resources,
      surface,
      'body',
      clock,
    )

    await adapter.load(new AbortController().signal)
    expect(resources.loadImage).toHaveBeenCalledTimes(4)
    adapter.enter()
    const layer = surface.layers[0]?.layer
    expect(layer?.images).toEqual(['asset://enter-a.png'])
    expect(clock.pending).toBe(1)

    clock.step(249)
    expect(layer?.images).toEqual(['asset://enter-a.png'])
    clock.step(1)
    clock.step(250)
    clock.step(250)
    clock.step(250)
    expect(layer?.images).toEqual([
      'asset://enter-a.png',
      'asset://enter-b.png',
      'asset://loop-a.png',
      'asset://loop-b.png',
      'asset://loop-a.png',
    ])

    adapter.setSuspended(true)
    expect(clock.pending).toBe(0)
    clock.step(10_000)
    expect(layer?.images.at(-1)).toBe('asset://loop-a.png')
    adapter.setSuspended(false)
    expect(clock.pending).toBe(1)
    clock.step(250)
    expect(layer?.images.at(-1)).toBe('asset://loop-b.png')

    adapter.dispose()
    expect(clock.pending).toBe(0)
    expect(layer?.disposed).toBe(true)
  })

  it('replays enter after a random idle interval at a loop boundary', async () => {
    const surface = new FakeSurface()
    const resources = loader()
    resources.loadFrameManifest = vi.fn(async () => ({
      schema_version: 1,
      fps: 4,
      enter: ['event-a.png', 'event-b.png'],
      loop: ['idle-a.png', 'idle-b.png'],
      replay_interval: { min_ms: 1_000, max_ms: 1_000 },
    }))
    const clock = new FakeAnimationClock()
    const adapter = new FrameAnimationAdapter(
      { renderer: 'frames', source: 'motion.json' },
      resources,
      surface,
      'body',
      clock,
      () => 0.5,
    )

    await adapter.load(new AbortController().signal)
    adapter.enter()
    const layer = surface.layers[0]?.layer
    for (let index = 0; index < 6; index += 1) clock.step(250)

    expect(layer?.images).toEqual([
      'asset://event-a.png',
      'asset://event-b.png',
      'asset://idle-a.png',
      'asset://idle-b.png',
      'asset://idle-a.png',
      'asset://idle-b.png',
      'asset://event-a.png',
    ])
    adapter.dispose()
  })

  it('does not consume a pending replay interval while suspended', async () => {
    const surface = new FakeSurface()
    const resources = loader()
    resources.loadFrameManifest = vi.fn(async () => ({
      schema_version: 1,
      fps: 4,
      enter: ['event.png'],
      loop: ['idle-a.png', 'idle-b.png'],
      replay_interval: { min_ms: 1_000, max_ms: 1_000 },
    }))
    const clock = new FakeAnimationClock()
    const adapter = new FrameAnimationAdapter(
      { renderer: 'frames', source: 'motion.json' },
      resources,
      surface,
      'body',
      clock,
      () => 0,
    )

    await adapter.load(new AbortController().signal)
    adapter.enter()
    clock.step(250)
    adapter.setSuspended(true)
    clock.step(10_000)
    adapter.setSuspended(false)
    clock.step(750)
    expect(
      surface.layers[0]?.layer.images.filter((source) => source === 'asset://event.png'),
    ).toHaveLength(1)
    clock.step(250)
    expect(surface.layers[0]?.layer.images.at(-1)).toBe('asset://event.png')
    adapter.dispose()
  })

  it('rejects invalid frame manifests before entering playback', async () => {
    const surface = new FakeSurface()
    const resources = loader()
    resources.loadFrameManifest = vi.fn(async () => ({
      schema_version: 1,
      fps: 31,
      enter: [],
      loop: ['frame.png'],
    }))
    const adapter = new FrameAnimationAdapter(
      { renderer: 'frames', source: 'motion.json' },
      resources,
      surface,
      'decoration',
      new FakeAnimationClock(),
    )

    await expect(adapter.load(new AbortController().signal)).rejects.toThrow(/fps/)
    expect(resources.loadImage).not.toHaveBeenCalled()
    adapter.dispose()
  })

  it('provides both built-in adapters through one format-independent factory', () => {
    const factory = new DefaultRendererAdapterFactory(
      loader(),
      new FakeSurface(),
      new FakeAnimationClock(),
    )

    expect(factory.availableRenderers).toEqual(new Set(['static', 'frames']))
    expect(factory.create({ renderer: 'static', source: 'body.png' }, 'body').renderer).toBe(
      'static',
    )
    expect(factory.create({ renderer: 'frames', source: 'body.json' }, 'body').renderer).toBe(
      'frames',
    )
  })

  it('keeps one session alive across motions and owns transition, suspension, and disposal', async () => {
    const surface = new FakeSurface()
    const resources = loader()
    const animationClock = new FakeAnimationClock()
    const transitionClock = new FakeTransitionClock()
    const adapters = new DefaultRendererAdapterFactory(resources, surface, animationClock)
    const session = new DefaultRendererSessionFactory(adapters).create({
      transitionClock,
    })
    const signal = new AbortController().signal

    const walk = await session.prepare(
      {
        motionKey: 'walk',
        motionInstanceId: 'tick:1',
        reducedMotion: false,
        backdrop: { renderer: 'static', source: 'night.png' },
        body: { renderer: 'frames', source: 'motion.json' },
        decoration: { renderer: 'static', source: 'walk.png' },
      },
      signal,
    )
    session.activate(walk, { durationMs: 120 })
    expect(walk.rendererNames).toEqual(['static', 'frames', 'static'])
    expect(surface.layers.slice(0, 3).map(({ role }) => role)).toEqual([
      'backdrop',
      'body',
      'decoration',
    ])
    expect(animationClock.pending).toBe(1)

    session.suspend()
    expect(animationClock.pending).toBe(0)
    session.resume()
    expect(animationClock.pending).toBe(1)

    const settle = await session.prepare(
      {
        motionKey: 'settle',
        motionInstanceId: 'tick:2',
        reducedMotion: false,
        body: { renderer: 'static', source: 'neutral.png' },
      },
      signal,
    )
    session.activate(settle, { durationMs: 120 })
    expect(settle.rendererNames).toEqual(['static'])
    expect(surface.layers[0]?.layer.disposed).toBe(false)
    expect(surface.layers[1]?.layer.disposed).toBe(false)
    expect(surface.layers[3]?.layer.opacities).toEqual([
      [0, 0],
      [1, 120],
    ])

    transitionClock.flush()
    expect(surface.layers[0]?.layer.disposed).toBe(true)
    expect(surface.layers[1]?.layer.disposed).toBe(true)
    expect(surface.layers[2]?.layer.disposed).toBe(true)
    expect(surface.layers[3]?.layer.disposed).toBe(false)

    session.dispose()
    expect(surface.layers[3]?.layer.disposed).toBe(true)
    expect(animationClock.pending).toBe(0)
  })

  it('aborts sibling resource loads when one prepared layer fails', async () => {
    const surface = new FakeSurface()
    let bodyAborted = false
    const resources: VisualResourceLoader = {
      loadImage: vi.fn((source: string, signal: AbortSignal) => {
        if (source === 'broken-decoration.png') {
          return Promise.reject(new Error('fixture load failure'))
        }
        return new Promise<string>((_resolve, reject) => {
          signal.addEventListener(
            'abort',
            () => {
              bodyAborted = true
              reject(new DOMException('aborted', 'AbortError'))
            },
            { once: true },
          )
        })
      }),
      loadFrameManifest: vi.fn(async () => ({})),
    }
    const session = new DefaultRendererSessionFactory(
      new DefaultRendererAdapterFactory(resources, surface),
    ).create()

    await expect(
      session.prepare(
        {
          motionKey: 'walk',
          motionInstanceId: 'tick:1',
          reducedMotion: false,
          body: { renderer: 'static', source: 'body.png' },
          decoration: { renderer: 'static', source: 'broken-decoration.png' },
        },
        new AbortController().signal,
      ),
    ).rejects.toThrow('fixture load failure')

    expect(bodyAborted).toBe(true)
    expect(surface.layers.every(({ layer }) => layer.disposed)).toBe(true)
  })

  it('aborts an in-flight preparation when its session is disposed', async () => {
    const surface = new FakeSurface()
    let loadSignal: AbortSignal | undefined
    const resources: VisualResourceLoader = {
      loadImage: vi.fn(
        (_source: string, signal: AbortSignal) =>
          new Promise<string>((_resolve, reject) => {
            loadSignal = signal
            signal.addEventListener(
              'abort',
              () => reject(new DOMException('aborted', 'AbortError')),
              { once: true },
            )
          }),
      ),
      loadFrameManifest: vi.fn(async () => ({})),
    }
    const session = new DefaultRendererSessionFactory(
      new DefaultRendererAdapterFactory(resources, surface),
    ).create()
    const preparation = session.prepare(
      {
        motionKey: 'neutral',
        motionInstanceId: 'empty:1',
        reducedMotion: false,
        body: { renderer: 'static', source: 'body.png' },
      },
      new AbortController().signal,
    )

    await Promise.resolve()
    session.dispose()

    await expect(preparation).rejects.toMatchObject({ name: 'AbortError' })
    expect(loadSignal?.aborted).toBe(true)
    expect(surface.layers[0]?.layer.disposed).toBe(true)
  })

  it('creates the default session owner without renderer I/O', () => {
    const surface = new FakeSurface()
    const resources = loader()
    const factory = new DefaultRendererSessionFactory(
      new DefaultRendererAdapterFactory(resources, surface),
    )

    expect(() => factory.create()).not.toThrow()
    expect(surface.layers).toHaveLength(0)
    expect(resources.loadImage).not.toHaveBeenCalled()
    expect(resources.loadFrameManifest).not.toHaveBeenCalled()
  })

  it('renders DOM layers as ordered, silent, non-text, pointer-transparent images', () => {
    const root = document.createElement('div')
    const surface = new DomVisualSurface(root)
    surface.createLayer('backdrop').setImage('asset://night.png')
    surface.createLayer('body').setImage('asset://body.png')
    const decoration = surface.createLayer('decoration')
    decoration.setImage('asset://cue.png')
    decoration.setOpacity(1, 100)

    const images = [...root.querySelectorAll('img')]
    expect(images.map((image) => image.dataset.visualLayer)).toEqual([
      'backdrop',
      'body',
      'decoration',
    ])
    expect(images.map((image) => image.style.zIndex)).toEqual(['0', '1', '2'])
    expect(images.every((image) => image.getAttribute('alt') === '')).toBe(true)
    expect(images.every((image) => image.getAttribute('aria-hidden') === 'true')).toBe(true)
    expect(images.every((image) => image.style.pointerEvents === 'none')).toBe(true)
    expect(root.textContent).toBe('')
  })
})
