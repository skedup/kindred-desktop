import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import type { SnapshotTransport } from './snapshotClient'

export type SourceKind = 'local' | 'remote'

export interface SourceProfile {
  label: string
  base_url: string
}

export interface WindowGeometry {
  x: number
  y: number
}

export interface ShellPreferences {
  schema_version: 1
  always_on_top: boolean
  active_source: SourceKind
  local: SourceProfile
  remote?: SourceProfile
  window?: WindowGeometry
}

export interface ShellCapabilities {
  transparent_window: boolean
}

export interface PreferencesEnvelope {
  preferences: ShellPreferences
  observation_generation: number
  capabilities: ShellCapabilities
}

interface SnapshotEnvelope {
  snapshot: unknown
  observation_generation: number
  source_label: string
}

export type NativeSuspensionReason =
  | 'screen-locked'
  | 'session-inactive'
  | 'sleep'
  | 'system-hidden'

export interface NativeSuspensionEvent {
  reason: NativeSuspensionReason
  suspended: boolean
  revision: number
}

export interface NativeSuspensionEnvelope {
  active_reasons: NativeSuspensionReason[]
  revision: number
}

export interface NativeMenuEvent {
  command: string
  always_on_top?: boolean
  error?: string
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted', 'AbortError')
}

let nativeCancellationBarrier: Promise<void> = Promise.resolve()

export class TauriSnapshotTransport implements SnapshotTransport {
  getSnapshot(signal: AbortSignal): Promise<unknown> {
    if (signal.aborted) return Promise.reject(abortError())
    const requestId = crypto.randomUUID()
    const invocation = nativeCancellationBarrier
      .then(() => invoke<SnapshotEnvelope>('fetch_visual_snapshot', { requestId }))
      .then((envelope) => envelope.snapshot)
    return new Promise((resolve, reject) => {
      const cleanup = () => signal.removeEventListener('abort', onAbort)
      const onAbort = () => {
        cleanup()
        nativeCancellationBarrier = invoke<void>('cancel_visual_snapshot', { requestId }).catch(
          () => undefined,
        )
        reject(abortError())
      }
      signal.addEventListener('abort', onAbort, { once: true })
      void invocation.then(resolve, reject).finally(cleanup)
    })
  }
}

export function loadPreferences(): Promise<PreferencesEnvelope> {
  return invoke<PreferencesEnvelope>('get_preferences')
}

export function savePreferences(preferences: ShellPreferences): Promise<PreferencesEnvelope> {
  return invoke<PreferencesEnvelope>('save_preferences', { preferences })
}

export function openKindred(observationGeneration: number): Promise<void> {
  return invoke('open_kindred', { observationGeneration })
}

export function showContextMenu(): Promise<void> {
  return invoke('show_context_menu')
}

export function getNativeSuspensions(): Promise<NativeSuspensionEnvelope> {
  return invoke<NativeSuspensionEnvelope>('get_native_suspensions')
}

export function listenForMenu(handler: (event: NativeMenuEvent) => void): Promise<UnlistenFn> {
  return listen<NativeMenuEvent>('kindred://menu', (event) => handler(event.payload))
}

export function listenForSuspension(
  handler: (event: NativeSuspensionEvent) => void,
): Promise<UnlistenFn> {
  return listen<NativeSuspensionEvent>('kindred://suspension', (event) => handler(event.payload))
}
