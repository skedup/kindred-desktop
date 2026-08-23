import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  VisualSnapshotClient,
  type ObservationConnectionState,
  type ObservationSnapshotContext,
  type SnapshotClientObserver,
  type SnapshotTransport,
} from './snapshotClient'
import type { VisualStateV1 } from './visualStateContract'

function ready(
  revision: number,
  action: string | null = 'walk',
  options: { source?: string; instance?: number; committedAt?: string } = {},
): VisualStateV1 {
  return {
    schema_version: 1,
    source_id: options.source ?? 'install:local',
    status: 'ready',
    revision,
    committed_at: options.committedAt ?? `2026-08-18T00:00:${String(revision).padStart(2, '0')}Z`,
    motion_instance_id: `tick:${options.instance ?? revision}`,
    action: action === null ? null : { name: action },
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function observer() {
  const snapshots: Array<{ snapshot: VisualStateV1 | null; context: ObservationSnapshotContext }> =
    []
  const connections: ObservationConnectionState[] = []
  const value: SnapshotClientObserver = {
    onSnapshot: (snapshot, context) => snapshots.push({ snapshot, context }),
    onConnection: (state) => connections.push(state),
  }
  return { value, snapshots, connections }
}

async function settle(): Promise<void> {
  for (let index = 0; index < 5; index += 1) await Promise.resolve()
}

beforeEach(() => vi.useFakeTimers())

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('VisualSnapshotClient', () => {
  it('polls immediately, permits one request in flight, and keeps a 10–12 second cadence', async () => {
    const first = deferred<unknown>()
    const transport: SnapshotTransport = {
      getSnapshot: vi
        .fn<SnapshotTransport['getSnapshot']>()
        .mockImplementationOnce(() => first.promise)
        .mockResolvedValue(ready(1)),
    }
    const events = observer()
    const client = new VisualSnapshotClient({
      transport,
      observer: events.value,
      random: () => 0.5,
    })

    client.start()
    expect(transport.getSnapshot).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(transport.getSnapshot).toHaveBeenCalledTimes(1)

    first.resolve(ready(1))
    await settle()
    expect(client.connection).toMatchObject({ health: 'healthy', next_request_ms: 11_000 })
    await vi.advanceTimersByTimeAsync(10_999)
    expect(transport.getSnapshot).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(transport.getSnapshot).toHaveBeenCalledTimes(2)
  })

  it('suspends timers and requests for hidden, locked, and sleeping states then resumes immediately', async () => {
    const requests: AbortSignal[] = []
    const pending = deferred<unknown>()
    const transport: SnapshotTransport = {
      getSnapshot: vi.fn((signal) => {
        requests.push(signal)
        return requests.length === 1 ? pending.promise : Promise.resolve(ready(2))
      }),
    }
    const events = observer()
    const client = new VisualSnapshotClient({ transport, observer: events.value, random: () => 0 })

    client.start()
    client.setSuspended('page-hidden', true)
    expect(requests[0]?.aborted).toBe(true)
    expect(client.connection.health).toBe('suspended')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(transport.getSnapshot).toHaveBeenCalledTimes(1)

    client.setSuspended('screen-locked', true)
    client.setSuspended('session-inactive', true)
    client.setSuspended('page-hidden', false)
    expect(transport.getSnapshot).toHaveBeenCalledTimes(1)
    client.setSuspended('screen-locked', false)
    expect(transport.getSnapshot).toHaveBeenCalledTimes(1)
    client.setSuspended('session-inactive', false)
    expect(transport.getSnapshot).toHaveBeenCalledTimes(2)
    await settle()
    expect(client.connection.health).toBe('healthy')
  })

  it('uses bounded exponential retry and manual retry without discarding the last snapshot', async () => {
    const transport: SnapshotTransport = {
      getSnapshot: vi
        .fn<SnapshotTransport['getSnapshot']>()
        .mockResolvedValueOnce(ready(1))
        .mockRejectedValueOnce(new TypeError('network detail must not escape'))
        .mockRejectedValueOnce(new Error('still unavailable'))
        .mockResolvedValue(ready(2)),
    }
    const events = observer()
    const client = new VisualSnapshotClient({ transport, observer: events.value, random: () => 0 })

    client.start()
    await settle()
    expect(client.snapshot).toEqual(ready(1))
    await vi.advanceTimersByTimeAsync(10_000)
    await settle()
    expect(client.connection).toMatchObject({
      health: 'retrying',
      diagnostic: 'transport_error',
      next_request_ms: 10_000,
    })
    expect(client.snapshot).toEqual(ready(1))

    await vi.advanceTimersByTimeAsync(10_000)
    await settle()
    expect(client.connection.next_request_ms).toBe(20_000)
    client.retryNow()
    expect(transport.getSnapshot).toHaveBeenCalledTimes(4)
    await settle()
    expect(client.snapshot).toEqual(ready(2))
    expect(client.connection.failure_count).toBe(0)
  })

  it('cancels an in-flight request before performing one immediate manual retry', async () => {
    const first = deferred<unknown>()
    let firstSignal: AbortSignal | undefined
    const transport: SnapshotTransport = {
      getSnapshot: vi
        .fn<SnapshotTransport['getSnapshot']>()
        .mockImplementationOnce((signal) => {
          firstSignal = signal
          signal.addEventListener(
            'abort',
            () => first.reject(new DOMException('aborted', 'AbortError')),
            { once: true },
          )
          return first.promise
        })
        .mockResolvedValue(ready(2)),
    }
    const events = observer()
    const client = new VisualSnapshotClient({ transport, observer: events.value, random: () => 0 })

    client.start()
    expect(transport.getSnapshot).toHaveBeenCalledTimes(1)
    client.retryNow()

    expect(firstSignal?.aborted).toBe(true)
    expect(transport.getSnapshot).toHaveBeenCalledTimes(2)
    await settle()
    expect(client.snapshot).toEqual(ready(2))
    expect(client.connection.health).toBe('healthy')
  })

  it('does not replay the unchanged committed snapshot during uncommitted work and rejects conflicts or regressions', async () => {
    const snapshots = [
      ready(4, 'walk', { instance: 2 }),
      ready(4, 'walk', { instance: 2 }),
      ready(4, 'eat', { instance: 2 }),
      ready(3, 'walk', { instance: 2 }),
    ]
    const transport: SnapshotTransport = {
      getSnapshot: vi.fn(async () => snapshots.shift()),
    }
    const events = observer()
    const client = new VisualSnapshotClient({ transport, observer: events.value, random: () => 0 })

    client.start()
    await settle()
    expect(events.snapshots).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(10_000)
    await settle()
    expect(events.snapshots).toHaveLength(1)
    expect(client.connection.health).toBe('healthy')

    await vi.advanceTimersByTimeAsync(10_000)
    await settle()
    expect(client.connection.diagnostic).toBe('snapshot_conflict')
    expect(client.snapshot).toEqual(ready(4, 'walk', { instance: 2 }))

    await vi.advanceTimersByTimeAsync(10_000)
    await settle()
    expect(client.connection.diagnostic).toBe('source_regression')
    expect(client.snapshot).toEqual(ready(4, 'walk', { instance: 2 }))
  })

  it('clears on profile changes, ignores stale generations, and fetches a fresh source baseline', async () => {
    const localPending = deferred<unknown>()
    const local: SnapshotTransport = { getSnapshot: vi.fn(() => localPending.promise) }
    const remote: SnapshotTransport = { getSnapshot: vi.fn(async () => ready(1, 'eat')) }
    const events = observer()
    const client = new VisualSnapshotClient({ transport: local, observer: events.value })

    client.start()
    client.changeSource(remote)
    expect(events.snapshots[0]).toEqual({
      snapshot: null,
      context: { generation: 2, reason: 'source-reset' },
    })
    expect(remote.getSnapshot).toHaveBeenCalledTimes(1)
    await settle()
    expect(client.snapshot).toEqual(ready(1, 'eat'))

    localPending.resolve(ready(99, 'walk'))
    await settle()
    expect(client.snapshot).toEqual(ready(1, 'eat'))

    const freshLocal: SnapshotTransport = {
      getSnapshot: vi.fn(async () => ready(2, 'walk')),
    }
    client.changeSource(freshLocal)
    await settle()
    expect(client.generation).toBe(3)
    expect(freshLocal.getSnapshot).toHaveBeenCalledTimes(1)
    expect(client.snapshot).toEqual(ready(2, 'walk'))
  })

  it('treats an endpoint source-id change as a reset and accepts its lower revision', async () => {
    const transport: SnapshotTransport = {
      getSnapshot: vi
        .fn<SnapshotTransport['getSnapshot']>()
        .mockResolvedValueOnce(ready(20, 'walk', { source: 'install:first' }))
        .mockResolvedValue(ready(1, 'eat', { source: 'install:second' })),
    }
    const events = observer()
    const client = new VisualSnapshotClient({ transport, observer: events.value, random: () => 0 })

    client.start()
    await settle()
    await vi.advanceTimersByTimeAsync(10_000)
    await settle()

    expect(events.snapshots.map(({ snapshot }) => snapshot)).toEqual([
      ready(20, 'walk', { source: 'install:first' }),
      null,
      ready(1, 'eat', { source: 'install:second' }),
    ])
    expect(client.snapshot).toEqual(ready(1, 'eat', { source: 'install:second' }))
  })

  it('does not expire a committed action during a quiet period or replay unchanged no-action', async () => {
    const noAction = ready(7, null, { instance: 5 })
    const transport: SnapshotTransport = { getSnapshot: vi.fn(async () => noAction) }
    const events = observer()
    const client = new VisualSnapshotClient({ transport, observer: events.value, random: () => 0 })

    client.start()
    await settle()
    await vi.advanceTimersByTimeAsync(120_000)
    await settle()

    expect(transport.getSnapshot).toHaveBeenCalledTimes(13)
    expect(events.snapshots).toHaveLength(1)
    expect(client.snapshot).toEqual(noAction)
  })
})
