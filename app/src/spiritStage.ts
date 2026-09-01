import type { VisualStateV1 } from './visualStateContract'
import type {
  ObservationConnectionState,
  ObservationSuspensionReason,
  ObservationSnapshotContext,
  SnapshotClientObserver,
} from './snapshotClient'
import type {
  PreparedRendererMotion,
  RendererSession,
  RendererSessionFactory,
  RendererTransitionClock,
} from './renderAdapters'
import {
  resolveVisualMotion,
  VisualPackResolutionError,
  type ResolvedVisualMotionV1,
  type VisualPackManifestV1,
} from './visualPack'

export type SpiritStageDiagnosticCode =
  | 'adapter_load_failed'
  | 'motion_fallback'
  | 'render_unavailable'

export interface SpiritStageDiagnostic {
  code: SpiritStageDiagnosticCode
  error_class?: string
  motion_key?: string
}

export interface SpiritStageState {
  pack_id: string
  identity: string
  generation: number
  connection: ObservationConnectionState
  motion_key: string | null
  motion_instance_id: string | null
  adapter_names: readonly string[]
  reduced_motion: boolean
  suspended: boolean
  diagnostic?: SpiritStageDiagnostic
}

export interface SpiritStageObserver {
  onState(state: SpiritStageState): void
}

export type TransitionClock = RendererTransitionClock

export interface SpiritStageOptions {
  manifest: VisualPackManifestV1
  rendererSessions: RendererSessionFactory
  observer?: SpiritStageObserver
  transitionClock?: TransitionClock
  crossfadeMs?: number
}

export interface PageVisibilityTarget {
  readonly visibilityState: 'hidden' | 'visible' | 'prerender'
  addEventListener(type: 'visibilitychange', listener: () => void): void
  removeEventListener(type: 'visibilitychange', listener: () => void): void
}

export interface ObservationSuspensionController {
  setSuspended(reason: ObservationSuspensionReason, suspended: boolean): void
}

export interface RendererSuspensionController {
  setSuspended(suspended: boolean): void
}

export function bindPageVisibility(
  target: PageVisibilityTarget,
  observation: ObservationSuspensionController,
  renderer: RendererSuspensionController,
): () => void {
  const synchronize = () => {
    const hidden = target.visibilityState !== 'visible'
    observation.setSuspended('page-hidden', hidden)
    renderer.setSuspended(hidden)
  }
  synchronize()
  target.addEventListener('visibilitychange', synchronize)
  return () => target.removeEventListener('visibilitychange', synchronize)
}

interface ActivePresentation {
  generation: number
  motionInstanceId: string
  action: string | null
  resolved: ResolvedVisualMotionV1
  rendererNames: readonly string[]
}

function errorClass(error: unknown): string {
  if (!(error instanceof Error)) return 'UnknownError'
  return /^[A-Za-z][A-Za-z0-9]{0,63}$/.test(error.name) ? error.name : 'Error'
}

function aborted(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

export class SpiritStage implements SnapshotClientObserver {
  private readonly manifest: VisualPackManifestV1
  private readonly rendererSessions: RendererSessionFactory
  private readonly observer: SpiritStageObserver | undefined
  private readonly transitionClock: TransitionClock | undefined
  private readonly crossfadeMs: number
  private rendererSession: RendererSession
  private generationValue = 1
  private connectionValue: ObservationConnectionState = {
    health: 'idle',
    generation: 1,
    failure_count: 0,
  }
  private current: ActivePresentation | null = null
  private desiredSnapshot: VisualStateV1 | null = null
  private reducedMotion = false
  private suspended = false
  private transitionSerial = 0
  private transitionAbort: AbortController | null = null
  private transitionPromise: Promise<void> | null = null
  private diagnostic: SpiritStageDiagnostic | undefined
  private disposed = false

  constructor(options: SpiritStageOptions) {
    this.manifest = options.manifest
    this.rendererSessions = options.rendererSessions
    this.observer = options.observer
    this.transitionClock = options.transitionClock
    this.crossfadeMs = Math.max(0, Math.floor(options.crossfadeMs ?? 160))
    this.rendererSession = this.createRendererSession()
  }

  get state(): SpiritStageState {
    return this.stageState()
  }

  async initialize(): Promise<void> {
    if (this.disposed || this.current !== null) return
    await this.transitionTo(null, `disconnected:${this.generationValue}`, this.generationValue, true)
  }

  onSnapshot(snapshot: VisualStateV1 | null, context: ObservationSnapshotContext): void {
    if (this.disposed || context.generation < this.generationValue) return
    if (context.reason === 'source-reset') {
      this.resetForSource(context.generation)
      return
    }
    if (context.generation > this.generationValue) this.resetForSource(context.generation)
    this.desiredSnapshot = snapshot
    if (snapshot === null || snapshot.status === 'empty') {
      this.startTransition(null, `empty:${context.generation}`, context.generation)
      return
    }
    this.startTransition(
      snapshot.action?.name ?? null,
      snapshot.motion_instance_id,
      context.generation,
    )
  }

  onConnection(state: ObservationConnectionState): void {
    if (this.disposed || state.generation < this.generationValue) return
    this.connectionValue = { ...state }
    this.emitState()
  }

  setReducedMotion(reduced: boolean): void {
    if (this.disposed || this.reducedMotion === reduced) return
    this.reducedMotion = reduced
    const snapshot = this.desiredSnapshot
    if (snapshot?.status === 'ready') {
      this.startTransition(
        snapshot.action?.name ?? null,
        snapshot.motion_instance_id,
        this.generationValue,
        true,
      )
    } else {
      this.startTransition(null, `empty:${this.generationValue}`, this.generationValue, true)
    }
    this.emitState()
  }

  setSuspended(suspended: boolean): void {
    if (this.disposed || this.suspended === suspended) return
    this.suspended = suspended
    if (suspended) this.rendererSession.suspend()
    else this.rendererSession.resume()
    this.emitState()
  }

  async whenIdle(): Promise<void> {
    await this.transitionPromise
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.transitionSerial += 1
    this.transitionAbort?.abort()
    this.transitionAbort = null
    this.rendererSession.dispose()
    this.current = null
    this.emitState()
  }

  private resetForSource(generation: number): void {
    this.generationValue = generation
    this.desiredSnapshot = null
    this.diagnostic = undefined
    this.transitionSerial += 1
    this.transitionAbort?.abort()
    this.transitionAbort = null
    this.rendererSession.dispose()
    this.rendererSession = this.createRendererSession()
    this.current = null
    this.emitState()
    this.startTransition(null, `disconnected:${generation}`, generation, true)
  }

  private startTransition(
    action: string | null,
    motionInstanceId: string,
    generation: number,
    force = false,
  ): void {
    const promise = this.transitionTo(action, motionInstanceId, generation, force)
    this.transitionPromise = promise
    void promise.finally(() => {
      if (this.transitionPromise === promise) this.transitionPromise = null
    })
  }

  private async transitionTo(
    action: string | null,
    motionInstanceId: string,
    generation: number,
    force: boolean,
  ): Promise<void> {
    if (this.disposed || generation !== this.generationValue) return
    if (
      !force &&
      this.current?.generation === generation &&
      this.current.motionInstanceId === motionInstanceId
    ) {
      return
    }
    const serial = ++this.transitionSerial
    this.transitionAbort?.abort()
    const controller = new AbortController()
    this.transitionAbort = controller
    const rendererSession = this.rendererSession
    const unavailable = new Set<string>()
    let lastError: unknown

    while (!controller.signal.aborted && !this.disposed) {
      let resolved: ResolvedVisualMotionV1
      try {
        resolved = resolveVisualMotion(this.manifest, action, {
          reducedMotion: this.reducedMotion,
          availableRenderers: this.rendererSessions.availableRenderers,
          unavailableMotionKeys: unavailable,
        })
      } catch (error) {
        if (error instanceof VisualPackResolutionError) {
          this.diagnostic = {
            code: 'render_unavailable',
            ...(lastError === undefined ? {} : { error_class: errorClass(lastError) }),
          }
          this.emitState()
          return
        }
        throw error
      }

      let prepared: PreparedRendererMotion | null = null
      try {
        prepared = await rendererSession.prepare(
          {
            motionKey: resolved.motion_key,
            motionInstanceId,
            reducedMotion: this.reducedMotion,
            ...(resolved.backdrop === undefined ? {} : { backdrop: resolved.backdrop }),
            body: resolved.presentation,
            ...(resolved.decoration === undefined ? {} : { decoration: resolved.decoration }),
          },
          controller.signal,
        )
        if (
          controller.signal.aborted ||
          this.disposed ||
          serial !== this.transitionSerial ||
          generation !== this.generationValue
        ) {
          rendererSession.discard(prepared)
          return
        }
        rendererSession.activate(prepared, { durationMs: this.crossfadeMs })
        this.current = {
          generation,
          motionInstanceId,
          action,
          resolved,
          rendererNames: prepared.rendererNames,
        }
        this.diagnostic =
          unavailable.size > 0
            ? {
                code: 'motion_fallback',
                motion_key: [...unavailable][0],
                ...(lastError === undefined ? {} : { error_class: errorClass(lastError) }),
              }
            : undefined
        this.emitState()
        return
      } catch (error) {
        if (prepared !== null) rendererSession.discard(prepared)
        if (aborted(error) || controller.signal.aborted) return
        lastError = error
        unavailable.add(resolved.motion_key)
        this.diagnostic = {
          code: 'adapter_load_failed',
          error_class: errorClass(error),
          motion_key: resolved.motion_key,
        }
        this.emitState()
      }
    }
  }

  private createRendererSession(): RendererSession {
    const session = this.rendererSessions.create({
      ...(this.transitionClock === undefined ? {} : { transitionClock: this.transitionClock }),
    })
    if (this.suspended) session.suspend()
    return session
  }

  private emitState(): void {
    this.observer?.onState(this.stageState())
  }

  private stageState(): SpiritStageState {
    return {
      pack_id: this.manifest.id,
      identity: this.manifest.identity,
      generation: this.generationValue,
      connection: { ...this.connectionValue },
      motion_key: this.current?.resolved.motion_key ?? null,
      motion_instance_id: this.current?.motionInstanceId ?? null,
      adapter_names: this.current?.rendererNames ?? [],
      reduced_motion: this.reducedMotion,
      suspended: this.suspended,
      ...(this.diagnostic === undefined ? {} : { diagnostic: { ...this.diagnostic } }),
    }
  }
}
