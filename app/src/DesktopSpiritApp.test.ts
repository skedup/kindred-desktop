// @vitest-environment jsdom

import { createApp, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const bridge = vi.hoisted(() => ({
  menuHandler: undefined as ((event: Record<string, unknown>) => void) | undefined,
  suspensionHandler: undefined as ((event: Record<string, unknown>) => void) | undefined,
  loadPreferences: vi.fn(),
  savePreferences: vi.fn(),
  getSnapshot: vi.fn(),
  getNativeSuspensions: vi.fn(),
  listenForMenu: vi.fn(),
  listenForSuspension: vi.fn(),
  showContextMenu: vi.fn(),
}))

vi.mock('./renderAdapters', () => ({
  BrowserVisualResourceLoader: class {},
  DefaultRendererAdapterFactory: class {},
  DefaultRendererSessionFactory: class {},
  DomVisualSurface: class {},
}))

vi.mock('./bundledPack', () => ({
  resolveBundledVisualPack: () => ({ manifest: {}, resolveSource: vi.fn() }),
}))

vi.mock('./spiritStage', () => ({
  SpiritStage: class {
    initialize = vi.fn(async () => undefined)
    setReducedMotion = vi.fn()
    setSuspended = vi.fn()
    onSnapshot = vi.fn()
    onConnection = vi.fn()
    dispose = vi.fn()
  },
}))

vi.mock('./tauriBridge', () => ({
  TauriSnapshotTransport: class {
    getSnapshot = bridge.getSnapshot
  },
  getNativeSuspensions: bridge.getNativeSuspensions,
  listenForMenu: bridge.listenForMenu,
  listenForSuspension: bridge.listenForSuspension,
  loadPreferences: bridge.loadPreferences,
  openKindred: vi.fn(async () => undefined),
  savePreferences: bridge.savePreferences,
  showContextMenu: bridge.showContextMenu,
}))

import DesktopSpiritApp from './DesktopSpiritApp.vue'

const envelope = {
  preferences: {
    schema_version: 1 as const,
    always_on_top: true,
    active_source: 'local' as const,
    local: { label: 'Local', base_url: 'http://127.0.0.1:8787' },
  },
  observation_generation: 1,
  capabilities: { transparent_window: true },
}

async function settle(): Promise<void> {
  for (let index = 0; index < 6; index += 1) {
    await Promise.resolve()
    await nextTick()
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

beforeEach(() => {
  bridge.menuHandler = undefined
  bridge.suspensionHandler = undefined
  bridge.loadPreferences.mockReset().mockResolvedValue(structuredClone(envelope))
  bridge.getSnapshot.mockReset().mockImplementation(() => new Promise(() => undefined))
  bridge.getNativeSuspensions.mockReset().mockResolvedValue({ revision: 0, active_reasons: [] })
  bridge.listenForMenu.mockReset().mockImplementation(
    async (handler: (event: Record<string, unknown>) => void) => {
      bridge.menuHandler = handler
      return vi.fn()
    },
  )
  bridge.listenForSuspension.mockReset().mockImplementation(
    async (handler: (event: Record<string, unknown>) => void) => {
      bridge.suspensionHandler = handler
      return vi.fn()
    },
  )
  bridge.showContextMenu.mockReset().mockResolvedValue(undefined)
  bridge.savePreferences.mockReset().mockImplementation(async (preferences: unknown) => ({
    ...structuredClone(envelope),
    preferences: structuredClone(preferences),
  }))
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('DesktopSpiritApp settings', () => {
  it('discards closed drafts and applies the authoritative native window level', async () => {
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(DesktopSpiritApp)
    app.mount(root)
    await settle()

    bridge.menuHandler?.({ command: 'settings' })
    await nextTick()
    const checkbox = root.querySelector<HTMLInputElement>('input[type="checkbox"]')
    const localLabel = root.querySelector<HTMLInputElement>('input[maxlength="80"]')
    expect(checkbox?.checked).toBe(true)
    expect(localLabel?.value).toBe('Local')

    checkbox?.click()
    if (localLabel !== null) {
      localLabel.value = 'Unsaved'
      localLabel.dispatchEvent(new Event('input'))
    }
    root.querySelector<HTMLButtonElement>('button[aria-label="关闭设置"]')?.click()
    await nextTick()

    bridge.menuHandler?.({ command: 'settings' })
    await nextTick()
    expect(root.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked).toBe(true)
    expect(root.querySelector<HTMLInputElement>('input[maxlength="80"]')?.value).toBe('Local')

    root.querySelector<HTMLInputElement>('input[type="checkbox"]')?.click()
    bridge.menuHandler?.({ command: 'always-on-top', always_on_top: false })
    await nextTick()
    expect(root.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked).toBe(false)

    app.unmount()
  })

  it('shows preference-load failures and lets the user recover in the same run', async () => {
    bridge.loadPreferences.mockRejectedValueOnce(new Error('preferences unavailable'))
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(DesktopSpiritApp)
    app.mount(root)
    await settle()

    expect(root.textContent).toContain('preferences unavailable')
    const reload = Array.from(root.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === '重新载入',
    )
    expect(reload).toBeDefined()

    reload?.click()
    await settle()
    expect(root.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked).toBe(true)
    expect(root.textContent).not.toContain('preferences unavailable')

    app.unmount()
  })

  it('fails closed when lifecycle registration fails and recovers without restarting', async () => {
    const tauri = await import('./tauriBridge')
    vi.mocked(tauri.listenForMenu).mockRejectedValueOnce(new Error('menu unavailable'))
    vi.mocked(tauri.listenForSuspension).mockRejectedValueOnce(new Error('lifecycle unavailable'))
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(DesktopSpiritApp)
    app.mount(root)
    await settle()

    expect(bridge.getSnapshot).toHaveBeenCalledTimes(0)
    expect(root.textContent).toContain('原生菜单监听不可用')

    const retry = Array.from(root.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === '立即重试',
    )
    retry?.click()
    await settle()
    expect(bridge.getSnapshot).toHaveBeenCalledTimes(1)

    app.unmount()
  })

  it('keeps the lifecycle listener and retries an unavailable current-state query', async () => {
    bridge.getNativeSuspensions.mockRejectedValueOnce(new Error('state unavailable'))
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(DesktopSpiritApp)
    app.mount(root)
    await settle()

    expect(bridge.listenForSuspension).toHaveBeenCalledTimes(1)
    expect(bridge.getNativeSuspensions).toHaveBeenCalledTimes(1)
    expect(bridge.getSnapshot).toHaveBeenCalledTimes(0)
    expect(root.textContent).toContain('系统暂停监听不可用：state unavailable')

    const retry = Array.from(root.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === '立即重试',
    )
    retry?.click()
    await settle()

    expect(bridge.listenForSuspension).toHaveBeenCalledTimes(1)
    expect(bridge.getNativeSuspensions).toHaveBeenCalledTimes(2)
    expect(bridge.getSnapshot).toHaveBeenCalledTimes(1)
    expect(root.textContent).not.toContain('state unavailable')

    app.unmount()
  })

  it('reports a native context-menu failure instead of leaking a rejected promise', async () => {
    bridge.showContextMenu.mockRejectedValueOnce(new Error('context unavailable'))
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(DesktopSpiritApp)
    app.mount(root)
    await settle()

    root.querySelector('main')?.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }))
    await settle()
    expect(root.textContent).toContain('原生菜单不可用：context unavailable')

    app.unmount()
  })

  it('does not restart observation when a listener resolves after unmount', async () => {
    const pending = deferred<() => void>()
    const unlisten = vi.fn()
    bridge.listenForSuspension.mockImplementationOnce(() => pending.promise)
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(DesktopSpiritApp)
    app.mount(root)
    await nextTick()
    app.unmount()

    pending.resolve(unlisten)
    await settle()
    expect(unlisten).toHaveBeenCalledTimes(1)
    expect(bridge.getSnapshot).toHaveBeenCalledTimes(0)
  })

  it('removes an installed lifecycle listener while its initial snapshot is pending', async () => {
    const pending = deferred<{ revision: number; active_reasons: string[] }>()
    const unlisten = vi.fn()
    bridge.listenForSuspension.mockResolvedValueOnce(unlisten)
    bridge.getNativeSuspensions.mockImplementationOnce(() => pending.promise)
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(DesktopSpiritApp)
    app.mount(root)
    await settle()

    app.unmount()
    expect(unlisten).toHaveBeenCalledTimes(1)
    pending.resolve({ revision: 0, active_reasons: [] })
    await settle()
    expect(bridge.getSnapshot).toHaveBeenCalledTimes(0)
  })

  it('keeps a failed save visible and prevents closing while it is in flight', async () => {
    const pending = deferred<never>()
    bridge.savePreferences.mockImplementationOnce(() => pending.promise)
    const root = document.createElement('div')
    document.body.append(root)
    const app = createApp(DesktopSpiritApp)
    app.mount(root)
    await settle()

    bridge.menuHandler?.({ command: 'settings' })
    await nextTick()
    const localLabel = root.querySelector<HTMLInputElement>('input[maxlength="80"]')
    if (localLabel !== null) {
      localLabel.value = 'Pending draft'
      localLabel.dispatchEvent(new Event('input'))
    }
    const save = Array.from(root.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === '保存',
    )
    save?.click()
    await nextTick()
    const close = root.querySelector<HTMLButtonElement>('button[aria-label="关闭设置"]')
    const fields = root.querySelector<HTMLFieldSetElement>('.settings-fields')
    expect(close?.disabled).toBe(true)
    expect(fields?.disabled).toBe(true)
    const checkbox = root.querySelector<HTMLInputElement>('input[type="checkbox"]')
    expect(checkbox?.matches(':disabled')).toBe(true)
    const checked = checkbox?.checked
    checkbox?.click()
    expect(checkbox?.checked).toBe(checked)
    bridge.menuHandler?.({ command: 'settings' })
    await nextTick()
    expect(root.querySelector<HTMLInputElement>('input[maxlength="80"]')?.value).toBe('Pending draft')
    close?.click()
    expect(root.querySelector('.settings-panel')).not.toBeNull()

    pending.reject(new Error('save unavailable'))
    await settle()
    expect(root.textContent).toContain('save unavailable')
    expect(root.querySelector('.settings-panel')).not.toBeNull()
    expect(root.querySelector<HTMLInputElement>('input[maxlength="80"]')?.value).toBe('Pending draft')

    app.unmount()
  })
})
