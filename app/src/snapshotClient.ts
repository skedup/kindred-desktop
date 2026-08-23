import {
  validateVisualStateV1,
  VisualSnapshotValidationError,
  type VisualStateReadyV1,
  type VisualStateV1,
} from './visualStateContract'

export type ObservationSuspensionReason =
  | 'page-hidden'
  | 'native-lifecycle-unavailable'
  | 'screen-locked'
  | 'session-inactive'
  | 'sleep'
  | 'system-hidden'

export type ObservationConnectionHealth =
  | 'idle'
  | 'connecting'
  | 'healthy'
  | 'retrying'
  | 'suspended'
  | 'stopped'

export type ObservationDiagnosticCode =
  | 'invalid_payload'
  | 'schema_mismatch'
  | 'snapshot_conflict'
  | 'source_regression'
  | 'transport_error'

export interface SnapshotTransport {
  getSnapshot(signal: AbortSignal): Promise<unknown>
}

export interface PollingClock {
  setTimeout(callback: () => void, delayMs: number): unknown
  clearTimeout(handle: unknown): void
}

export interface ObservationConnectionState {
  health: ObservationConnectionHealth
  generation: number
  failure_count: number
  next_request_ms?: number
  diagnostic?: ObservationDiagnosticCode
}

export interface ObservationSnapshotContext {
  generation: number
  reason: 'accepted' | 'source-reset'
}

export interface SnapshotClientObserver {
  onSnapshot(snapshot: VisualStateV1 | null, context: ObservationSnapshotContext): void
  onConnection(state: ObservationConnectionState): void
}

export interface SnapshotClientOptions {
  transport: SnapshotTransport
  observer: SnapshotClientObserver
  clock?: PollingClock
  random?: () => number
}

class SnapshotOrderingError extends Error {
  constructor(readonly code: 'snapshot_conflict' | 'source_regression') {
    super(code)
    this.name = 'SnapshotOrderingError'
  }
}

const NORMAL_MIN_MS = 10_000
const NORMAL_JITTER_MS = 2_000
const RETRY_MAX_MS = 300_000
const DEFAULT_CLOCK: PollingClock = {
  setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
}

function fingerprint(snapshot: VisualStateV1): string {
  if (snapshot.status === 'empty') return JSON.stringify([1, snapshot.source_id, 'empty'])
  return JSON.stringify([
    1,
    snapshot.source_id,
    'ready',
    snapshot.revision,
    snapshot.committed_at,
    snapshot.motion_instance_id,
    snapshot.action?.name ?? null,
  ])
}

function ready(snapshot: VisualStateV1 | null): VisualStateReadyV1 | null {
  return snapshot?.status === 'ready' ? snapshot : null
}

function boundedRandom(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(Math.max(value, 0), 0.999_999)
}

function abortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

export class VisualSnapshotClient {
  private transport: SnapshotTransport
  private readonly observer: SnapshotClientObserver
  private readonly clock: PollingClock
  private readonly random: () => number
  private running = false
  private generationValue = 1
  private healthValue: ObservationConnectionHealth = 'idle'
  private diagnosticValue: ObservationDiagnosticCode | undefined
  private failures = 0
  private nextRequestMs: number | undefined
  private timer: unknown | undefined
  private requestSerial = 0
  private activeRequest: { serial: number; generation: number; controller: AbortController } | null =
    null
  private readonly suspensions = new Set<ObservationSuspensionReason>()
  private sourceId: string | null = null
  private snapshotValue: VisualStateV1 | null = null
  private snapshotFingerprint: string | null = null

  constructor(options: SnapshotClientOptions) {
    this.transport = options.transport
    this.observer = options.observer
    this.clock = options.clock ?? DEFAULT_CLOCK
    this.random = options.random ?? Math.random
  }

  get generation(): number {
    return this.generationValue
  }

  get snapshot(): VisualStateV1 | null {
    return this.snapshotValue
  }

  get connection(): ObservationConnectionState {
    return this.connectionState()
  }

  start(): void {
    if (this.running) return
    this.running = true
    if (this.suspensions.size > 0) {
      this.setHealth('suspended')
      return
    }
    this.requestImmediately()
  }

  stop(): void {
    if (!this.running && this.healthValue === 'stopped') return
    this.running = false
    this.cancelTimer()
    this.cancelRequest()
    this.setHealth('stopped')
  }

  changeSource(transport: SnapshotTransport): void {
    this.transport = transport
    this.generationValue += 1
    this.failures = 0
    this.sourceId = null
    this.snapshotValue = null
    this.snapshotFingerprint = null
    this.cancelTimer()
    this.cancelRequest()
    this.observer.onSnapshot(null, {
      generation: this.generationValue,
      reason: 'source-reset',
    })
    if (this.running && this.suspensions.size === 0) this.requestImmediately()
    else this.setHealth(this.running ? 'suspended' : 'idle')
  }

  setSuspended(reason: ObservationSuspensionReason, suspended: boolean): void {
    const wasSuspended = this.suspensions.size > 0
    if (suspended) this.suspensions.add(reason)
    else this.suspensions.delete(reason)
    const isSuspended = this.suspensions.size > 0
    if (wasSuspended === isSuspended) return
    if (isSuspended) {
      this.cancelTimer()
      this.cancelRequest()
      if (this.running) this.setHealth('suspended')
    } else if (this.running) {
      this.requestImmediately()
    }
  }

  retryNow(): void {
    this.failures = 0
    this.diagnosticValue = undefined
    if (!this.running || this.suspensions.size > 0) {
      this.emitConnection()
      return
    }
    this.cancelTimer()
    this.cancelRequest()
    this.requestImmediately()
  }

  private requestImmediately(): void {
    if (!this.running || this.suspensions.size > 0 || this.activeRequest !== null) return
    this.cancelTimer()
    void this.requestSnapshot()
  }

  private async requestSnapshot(): Promise<void> {
    const serial = ++this.requestSerial
    const generation = this.generationValue
    const controller = new AbortController()
    this.activeRequest = { serial, generation, controller }
    this.nextRequestMs = undefined
    this.setHealth('connecting')
    try {
      const value = await this.transport.getSnapshot(controller.signal)
      if (!this.isCurrentRequest(serial, generation)) return
      const snapshot = validateVisualStateV1(value)
      this.acceptSnapshot(snapshot)
      this.failures = 0
      this.diagnosticValue = undefined
      this.setHealth('healthy')
      this.schedule(this.healthyDelay())
    } catch (error) {
      if (!this.isCurrentRequest(serial, generation) || abortError(error)) return
      this.failures += 1
      this.diagnosticValue = this.diagnosticFor(error)
      this.setHealth('retrying')
      this.schedule(this.retryDelay())
    } finally {
      if (this.isCurrentRequest(serial, generation)) this.activeRequest = null
    }
  }

  private acceptSnapshot(snapshot: VisualStateV1): void {
    if (this.sourceId !== null && this.sourceId !== snapshot.source_id) {
      this.sourceId = null
      this.snapshotValue = null
      this.snapshotFingerprint = null
      this.observer.onSnapshot(null, {
        generation: this.generationValue,
        reason: 'source-reset',
      })
    }
    if (this.sourceId === null) this.sourceId = snapshot.source_id

    const currentReady = ready(this.snapshotValue)
    const nextReady = ready(snapshot)
    if (currentReady !== null && nextReady === null) {
      throw new SnapshotOrderingError('source_regression')
    }
    if (currentReady !== null && nextReady !== null) {
      if (nextReady.revision < currentReady.revision) {
        throw new SnapshotOrderingError('source_regression')
      }
      if (nextReady.revision === currentReady.revision) {
        if (fingerprint(snapshot) !== this.snapshotFingerprint) {
          throw new SnapshotOrderingError('snapshot_conflict')
        }
        return
      }
    }
    const nextFingerprint = fingerprint(snapshot)
    if (nextFingerprint === this.snapshotFingerprint) return
    this.snapshotValue = snapshot
    this.snapshotFingerprint = nextFingerprint
    this.observer.onSnapshot(snapshot, {
      generation: this.generationValue,
      reason: 'accepted',
    })
  }

  private isCurrentRequest(serial: number, generation: number): boolean {
    return (
      this.activeRequest?.serial === serial &&
      this.activeRequest.generation === generation &&
      this.generationValue === generation
    )
  }

  private schedule(delayMs: number): void {
    if (!this.running || this.suspensions.size > 0) return
    this.cancelTimer()
    this.nextRequestMs = delayMs
    this.timer = this.clock.setTimeout(() => {
      this.timer = undefined
      this.nextRequestMs = undefined
      this.requestImmediately()
    }, delayMs)
    this.emitConnection()
  }

  private healthyDelay(): number {
    return NORMAL_MIN_MS + Math.floor(boundedRandom(this.random()) * (NORMAL_JITTER_MS + 1))
  }

  private retryDelay(): number {
    const exponent = Math.min(this.failures - 1, 20)
    const base = Math.min(NORMAL_MIN_MS * 2 ** exponent, RETRY_MAX_MS)
    const jitterRoom = Math.min(Math.floor(base * 0.2), RETRY_MAX_MS - base)
    return base + Math.floor(boundedRandom(this.random()) * (jitterRoom + 1))
  }

  private diagnosticFor(error: unknown): ObservationDiagnosticCode {
    if (error instanceof VisualSnapshotValidationError) return error.code
    if (error instanceof SnapshotOrderingError) return error.code
    return 'transport_error'
  }

  private cancelTimer(): void {
    if (this.timer === undefined) return
    this.clock.clearTimeout(this.timer)
    this.timer = undefined
    this.nextRequestMs = undefined
  }

  private cancelRequest(): void {
    const request = this.activeRequest
    this.activeRequest = null
    request?.controller.abort()
  }

  private setHealth(health: ObservationConnectionHealth): void {
    this.healthValue = health
    this.emitConnection()
  }

  private emitConnection(): void {
    this.observer.onConnection(this.connectionState())
  }

  private connectionState(): ObservationConnectionState {
    return {
      health: this.healthValue,
      generation: this.generationValue,
      failure_count: this.failures,
      ...(this.nextRequestMs === undefined ? {} : { next_request_ms: this.nextRequestMs }),
      ...(this.diagnosticValue === undefined ? {} : { diagnostic: this.diagnosticValue }),
    }
  }
}
