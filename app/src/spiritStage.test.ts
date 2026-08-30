import { describe, expect, it, vi } from 'vitest'
import defaultPackJson from '../../visual-packs/kindred-default/manifest.json'
import type {
  RendererAdapter,
  RendererAdapterFactory,
  RendererSession,
  RendererSessionFactory,
  RendererSessionOptions,
  VisualLayerRole,
} from './renderAdapters'
import { DefaultRendererSessionFactory } from './renderAdapters'
import {
  bindPageVisibility,
  SpiritStage,
  type PageVisibilityTarget,
  type SpiritStageState,
  type TransitionClock,
} from './spiritStage'
import {
  VisualSnapshotClient,
  type PollingClock,
  type SnapshotTransport,
} from './snapshotClient'
import { validateVisualPackManifest, type VisualAssetDescriptorV1 } from './visualPack'
import type { VisualStateV1 } from './visualStateContract'

function ready(
  revision: number,
  action: string | null,
  instance: number,
  source = 'install:fixture',
): VisualStateV1 {
  return {
    schema_version: 1,
    source_id: source,
    status: 'ready',
    revision,
    committed_at: `2026-08-18T00:00:${String(revision).padStart(2, '0')}Z`,
    motion_instance_id: `tick:${instance}`,
    action: action === null ? null : { name: action },
  }
}

class FakeAdapter implements RendererAdapter {
  readonly renderer
  readonly load = vi.fn(async (_signal: AbortSignal) => {})
  readonly enter = vi.fn()
  readonly setSuspended = vi.fn()
  readonly setOpacity = vi.fn()
  readonly dispose = vi.fn()

  constructor(
    readonly descriptor: VisualAssetDescriptorV1,
    readonly role: VisualLayerRole,
  ) {
    this.renderer = descriptor.renderer
  }
}

class FakeFactory implements RendererAdapterFactory {
  readonly availableRenderers = new Set(['static', 'frames'] as const)
  readonly created: FakeAdapter[] = []
  readonly failSources = new Set<string>()
  readonly failCreateSources = new Set<string>()
  readonly failEnterSources = new Set<string>()
  readonly pendingSources = new Map<string, ReturnType<typeof deferred<void>>>()

  create(descriptor: VisualAssetDescriptorV1, role: VisualLayerRole): RendererAdapter {
    if (this.failCreateSources.has(descriptor.source)) {
      const error = new Error('factory details must stay private')
      error.name = 'FactoryFailure'
      throw error
    }
    const adapter = new FakeAdapter(descriptor, role)
    adapter.enter.mockImplementation(() => {
      if (this.failEnterSources.has(descriptor.source)) {
        const error = new Error('activation details must stay private')
        error.name = 'ActivationFailure'
        throw error
      }
    })
    adapter.load.mockImplementation(async (signal) => {
      const pending = this.pendingSources.get(descriptor.source)
      if (pending !== undefined) await pending.promise
      if (signal.aborted) throw new DOMException('aborted', 'AbortError')
      if (this.failSources.has(descriptor.source)) {
        const error = new Error(`must not leak ${descriptor.source}`)
        error.name = 'AssetFailure'
        throw error
      }
    })
    this.created.push(adapter)
    return adapter
  }
}

class CountingSessionFactory implements RendererSessionFactory {
  readonly availableRenderers
  readonly sessions: RendererSession[] = []
  private readonly delegate: DefaultRendererSessionFactory

  constructor(adapters: RendererAdapterFactory) {
    this.delegate = new DefaultRendererSessionFactory(adapters)
    this.availableRenderers = this.delegate.availableRenderers
  }

  create(options?: RendererSessionOptions): RendererSession {
    const session = this.delegate.create(options)
    this.sessions.push(session)
    return session
  }
}

class FakeTransitionClock implements TransitionClock {
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

class FakePollingClock implements PollingClock {
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
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function accepted(generation = 1) {
  return { generation, reason: 'accepted' as const }
}

function reset(generation: number) {
  return { generation, reason: 'source-reset' as const }
}

async function settle(): Promise<void> {
  for (let index = 0; index < 6; index += 1) await Promise.resolve()
}

function createStage(options: { crossfadeMs?: number } = {}) {
  const factory = new FakeFactory()
  const states: SpiritStageState[] = []
  const clock = new FakeTransitionClock()
  const sessions = new CountingSessionFactory(factory)
  const stage = new SpiritStage({
    manifest: validateVisualPackManifest(defaultPackJson),
    rendererSessions: sessions,
    observer: { onState: (state) => states.push(state) },
    transitionClock: clock,
    crossfadeMs: options.crossfadeMs ?? 120,
  })
  return { stage, factory, sessions, states, clock }
}

describe('SpiritStage', () => {
  it('renders neutral first, preserves an unchanged motion instance, and replays re-entry', async () => {
    const { stage, factory, sessions, clock } = createStage()
    await stage.initialize()
    expect(stage.state).toMatchObject({
      identity: 'kindred-resident-v1',
      motion_key: 'neutral',
      motion_instance_id: 'disconnected:1',
    })

    stage.onSnapshot(ready(1, 'walk', 1), accepted())
    await stage.whenIdle()
    expect(stage.state).toMatchObject({ motion_key: 'walk', motion_instance_id: 'tick:1' })
    expect(factory.created.slice(-2).map((adapter) => [adapter.renderer, adapter.role])).toEqual([
      ['frames', 'body'],
      ['static', 'decoration'],
    ])
    const createdAfterWalk = factory.created.length

    stage.onSnapshot(ready(2, 'walk', 1), accepted())
    await stage.whenIdle()
    expect(factory.created).toHaveLength(createdAfterWalk)

    stage.onSnapshot(ready(3, 'eat', 2), accepted())
    await stage.whenIdle()
    expect(factory.created).toHaveLength(createdAfterWalk + 2)
    expect(stage.state).toMatchObject({ motion_key: 'eat', motion_instance_id: 'tick:2' })

    stage.onSnapshot(ready(4, 'walk', 3), accepted())
    await stage.whenIdle()
    expect(factory.created).toHaveLength(createdAfterWalk + 4)
    expect(stage.state).toMatchObject({ motion_key: 'walk', motion_instance_id: 'tick:3' })
    expect(sessions.sessions).toHaveLength(1)
    clock.flush()
    expect(factory.created.slice(0, createdAfterWalk).every((adapter) => adapter.dispose.mock.calls.length > 0))
      .toBe(true)
  })

  it('does not replay unchanged no-action but does replay a new no-action instance', async () => {
    const { stage, factory } = createStage({ crossfadeMs: 0 })
    stage.onSnapshot(ready(4, null, 3), accepted())
    await stage.whenIdle()
    const firstCount = factory.created.length
    expect(stage.state.motion_key).toBe('neutral')

    stage.onSnapshot(ready(5, null, 3), accepted())
    await stage.whenIdle()
    expect(factory.created).toHaveLength(firstCount)

    stage.onSnapshot(ready(6, null, 6), accepted())
    await stage.whenIdle()
    expect(factory.created).toHaveLength(firstCount + 1)
    expect(stage.state.motion_instance_id).toBe('tick:6')
  })

  it('keeps the latest action running through connection loss and quiet periods', async () => {
    const { stage, factory } = createStage()
    stage.onSnapshot(ready(1, 'settle', 1), accepted())
    await stage.whenIdle()
    const adapters = factory.created.slice()

    stage.onConnection({
      health: 'retrying',
      generation: 1,
      failure_count: 3,
      next_request_ms: 40_000,
      diagnostic: 'transport_error',
    })
    expect(stage.state.motion_key).toBe('settle')
    expect(stage.state.connection.health).toBe('retrying')
    expect(factory.created).toEqual(adapters)
    expect(adapters.every((adapter) => adapter.dispose.mock.calls.length === 0)).toBe(true)
  })

  it('clears Local on Remote selection and never revives it while Remote is unavailable', async () => {
    const { stage, factory, sessions } = createStage({ crossfadeMs: 0 })
    stage.onSnapshot(ready(10, 'walk', 8, 'install:local'), accepted())
    await stage.whenIdle()
    const localAdapters = factory.created.slice()

    stage.onSnapshot(null, reset(2))
    await stage.whenIdle()
    const createdAfterReset = factory.created.length
    expect(localAdapters.every((adapter) => adapter.dispose.mock.calls.length > 0)).toBe(true)
    expect(stage.state).toMatchObject({
      generation: 2,
      motion_key: 'neutral',
      motion_instance_id: 'disconnected:2',
    })
    expect(sessions.sessions).toHaveLength(2)

    stage.onConnection({
      health: 'retrying',
      generation: 2,
      failure_count: 1,
      diagnostic: 'transport_error',
    })
    await stage.whenIdle()
    expect(stage.state.motion_key).toBe('neutral')
    expect(factory.created).toHaveLength(createdAfterReset)

    stage.onSnapshot(ready(1, 'eat', 1, 'install:remote'), accepted(2))
    await stage.whenIdle()
    expect(stage.state).toMatchObject({ motion_key: 'eat', motion_instance_id: 'tick:1' })
  })

  it('falls back deterministically when an action adapter fails without exposing error details', async () => {
    const { stage, factory, states } = createStage({ crossfadeMs: 0 })
    factory.failSources.add('motions/walk.json')

    stage.onSnapshot(ready(1, 'walk', 1), accepted())
    await stage.whenIdle()

    expect(stage.state).toMatchObject({
      motion_key: 'neutral',
      diagnostic: {
        code: 'motion_fallback',
        error_class: 'AssetFailure',
        motion_key: 'walk',
      },
    })
    expect(JSON.stringify(states)).not.toContain('must not leak')
    expect(JSON.stringify(states)).not.toContain('motions/walk.json')
  })

  it('also falls back when adapter construction fails before resource loading', async () => {
    const { stage, factory } = createStage({ crossfadeMs: 0 })
    factory.failCreateSources.add('assets/decorations/walk.png')

    stage.onSnapshot(ready(1, 'walk', 1), accepted())
    await stage.whenIdle()

    expect(stage.state).toMatchObject({
      motion_key: 'neutral',
      diagnostic: { code: 'motion_fallback', error_class: 'FactoryFailure' },
    })
    expect(
      factory.created.find((adapter) => adapter.descriptor.source === 'motions/walk.json')
        ?.dispose,
    ).toHaveBeenCalledTimes(1)
    expect(JSON.stringify(stage.state)).not.toContain('factory details')
  })

  it('falls back when session activation fails and keeps private details out of state', async () => {
    const { stage, factory } = createStage({ crossfadeMs: 0 })
    factory.failEnterSources.add('motions/walk.json')

    stage.onSnapshot(ready(1, 'walk', 1), accepted())
    await stage.whenIdle()

    expect(stage.state).toMatchObject({
      motion_key: 'neutral',
      diagnostic: {
        code: 'motion_fallback',
        error_class: 'ActivationFailure',
        motion_key: 'walk',
      },
    })
    expect(JSON.stringify(stage.state)).not.toContain('activation details')
  })

  it('discards stale adapter loads after a newer motion instance arrives', async () => {
    const { stage, factory } = createStage({ crossfadeMs: 0 })
    const pending = deferred<void>()
    factory.pendingSources.set('motions/walk.json', pending)

    stage.onSnapshot(ready(1, 'walk', 1), accepted())
    const staleAdapters = factory.created.slice()
    stage.onSnapshot(ready(2, null, 2), accepted())
    await stage.whenIdle()
    expect(stage.state).toMatchObject({ motion_key: 'neutral', motion_instance_id: 'tick:2' })

    pending.resolve()
    await settle()
    expect(staleAdapters.every((adapter) => adapter.dispose.mock.calls.length > 0)).toBe(true)
    expect(stage.state.motion_instance_id).toBe('tick:2')
  })

  it('switches all built-in actions to their explicit static reduced-motion compositions', async () => {
    const { stage, factory } = createStage({ crossfadeMs: 0 })
    stage.setReducedMotion(true)
    const manifest = validateVisualPackManifest(defaultPackJson)
    const actions = Object.keys(manifest.action_motions)

    for (const [index, action] of actions.entries()) {
      stage.onSnapshot(ready(index + 1, action, index + 1), accepted())
      await stage.whenIdle()
      expect(stage.state.adapter_names).toEqual(['static', 'static'])
      const latest = factory.created.slice(-2)
      const motionKey = manifest.action_motions[action]!
      expect(latest[0]?.descriptor.source).toBe(manifest.motions[motionKey]!.reduced_motion.source)
      expect(latest[1]?.descriptor.source).toContain(`/${action.replaceAll('_', '-')}.png`)
    }
    expect(stage.state.identity).toBe('kindred-resident-v1')
  })

  it('propagates suspension without restarting the active animation', async () => {
    const { stage, factory } = createStage()
    stage.onSnapshot(ready(1, 'walk', 1), accepted())
    await stage.whenIdle()
    const active = factory.created.slice(-2)

    stage.setSuspended(true)
    stage.setSuspended(false)

    expect(active[0]?.enter).toHaveBeenCalledTimes(1)
    expect(active[0]?.setSuspended.mock.calls.map(([value]) => value)).toEqual([
      false,
      true,
      false,
    ])
    expect(stage.state.suspended).toBe(false)
  })

  it('binds page visibility to both observation and rendering suspension', () => {
    let listener: (() => void) | undefined
    const target: PageVisibilityTarget = {
      visibilityState: 'hidden',
      addEventListener: (_type, callback) => {
        listener = callback
      },
      removeEventListener: (_type, callback) => {
        if (listener === callback) listener = undefined
      },
    }
    const observation = { setSuspended: vi.fn() }
    const renderer = { setSuspended: vi.fn() }

    const unbind = bindPageVisibility(target, observation, renderer)
    expect(observation.setSuspended).toHaveBeenCalledWith('page-hidden', true)
    expect(renderer.setSuspended).toHaveBeenCalledWith(true)

    Object.defineProperty(target, 'visibilityState', { value: 'visible' })
    listener?.()
    expect(observation.setSuspended).toHaveBeenLastCalledWith('page-hidden', false)
    expect(renderer.setSuspended).toHaveBeenLastCalledWith(false)

    unbind()
    expect(listener).toBeUndefined()
  })

  it('integrates source resets with the snapshot client without reviving inactive state', async () => {
    const { stage, factory } = createStage({ crossfadeMs: 0 })
    const initialLocal: SnapshotTransport = {
      getSnapshot: vi.fn(async () => ready(20, 'settle', 20, 'install:local')),
    }
    const unavailableRemote: SnapshotTransport = {
      getSnapshot: vi.fn(async () => {
        throw new TypeError('remote endpoint details')
      }),
    }
    const freshLocal: SnapshotTransport = {
      getSnapshot: vi.fn(async () => ready(1, 'walk', 1, 'install:local')),
    }
    const client = new VisualSnapshotClient({
      transport: initialLocal,
      observer: stage,
      clock: new FakePollingClock(),
      random: () => 0,
    })

    client.start()
    await settle()
    await stage.whenIdle()
    expect(stage.state).toMatchObject({ generation: 1, motion_key: 'settle' })
    const inactiveLocal = factory.created.slice()

    client.changeSource(unavailableRemote)
    await settle()
    await stage.whenIdle()
    expect(stage.state).toMatchObject({
      generation: 2,
      motion_key: 'neutral',
      connection: { health: 'retrying', diagnostic: 'transport_error' },
    })
    expect(inactiveLocal.every((adapter) => adapter.dispose.mock.calls.length > 0)).toBe(true)

    client.changeSource(freshLocal)
    await settle()
    await stage.whenIdle()
    expect(stage.state).toMatchObject({ generation: 3, motion_key: 'walk' })
    expect(freshLocal.getSnapshot).toHaveBeenCalledTimes(1)
  })
})
