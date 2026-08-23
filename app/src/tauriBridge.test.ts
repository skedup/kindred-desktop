import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { invokeMock, listenMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  listenMock: vi.fn(),
}))

vi.mock('@tauri-apps/api/core', () => ({ invoke: invokeMock }))
vi.mock('@tauri-apps/api/event', () => ({ listen: listenMock }))

import { getNativeSuspensions, listenForMenu, TauriSnapshotTransport } from './tauriBridge'

const REQUEST_ID = '89abcdef-0123-4567-89ab-cdef01234567'

beforeEach(() => {
  invokeMock.mockReset()
  listenMock.mockReset()
  vi.stubGlobal('crypto', { randomUUID: () => REQUEST_ID })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Tauri snapshot bridge', () => {
  it('passes only an opaque token to the fixed native fetch command', async () => {
    invokeMock.mockResolvedValue({
      snapshot: { schema_version: 1, source_id: 'fixture', status: 'empty' },
      observation_generation: 1,
      source_label: 'Local',
    })

    const result = await new TauriSnapshotTransport().getSnapshot(
      new AbortController().signal,
    )

    expect(result).toEqual({ schema_version: 1, source_id: 'fixture', status: 'empty' })
    expect(invokeMock).toHaveBeenCalledWith('fetch_visual_snapshot', {
      requestId: REQUEST_ID,
    })
  })

  it('forwards abort to native cancellation before later requests cross the bridge', async () => {
    let resolveFetch: ((value: unknown) => void) | undefined
    invokeMock.mockImplementation((command: string) => {
      if (command === 'fetch_visual_snapshot') {
        return new Promise((resolve) => {
          resolveFetch = resolve
        })
      }
      return Promise.resolve()
    })
    const controller = new AbortController()
    const request = new TauriSnapshotTransport().getSnapshot(controller.signal)
    await vi.waitFor(() =>
      expect(invokeMock).toHaveBeenCalledWith('fetch_visual_snapshot', {
        requestId: REQUEST_ID,
      }),
    )

    controller.abort()
    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
    await vi.waitFor(() =>
      expect(invokeMock).toHaveBeenCalledWith('cancel_visual_snapshot', {
        requestId: REQUEST_ID,
      }),
    )
    resolveFetch?.({ snapshot: { schema_version: 1, source_id: 'ignored', status: 'empty' } })
  })

  it('returns the authoritative native suspension snapshot', async () => {
    invokeMock.mockResolvedValue({ revision: 3, active_reasons: ['screen-locked'] })

    await expect(getNativeSuspensions()).resolves.toEqual({
      revision: 3,
      active_reasons: ['screen-locked'],
    })
    expect(invokeMock).toHaveBeenCalledWith('get_native_suspensions')
  })

  it('forwards structured native menu state instead of inferring it locally', async () => {
    let callback: ((event: { payload: unknown }) => void) | undefined
    const unlisten = vi.fn()
    listenMock.mockImplementation((_event: string, handler: typeof callback) => {
      callback = handler
      return Promise.resolve(unlisten)
    })
    const handler = vi.fn()

    await expect(listenForMenu(handler)).resolves.toBe(unlisten)
    callback?.({
      payload: { command: 'always-on-top', always_on_top: false },
    })

    expect(handler).toHaveBeenCalledWith({ command: 'always-on-top', always_on_top: false })
  })
})
