<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  BrowserVisualResourceLoader,
  DefaultRendererAdapterFactory,
  DefaultRendererSessionFactory,
  DomVisualSurface,
} from './renderAdapters'
import { resolveBundledVisualPack } from './bundledPack'
import {
  type ObservationConnectionState,
  type ObservationSuspensionReason,
  VisualSnapshotClient,
} from './snapshotClient'
import { SpiritStage, type SpiritStageState } from './spiritStage'
import {
  getNativeSuspensions,
  listenForMenu,
  listenForSuspension,
  loadPreferences,
  openKindred,
  savePreferences,
  showContextMenu,
  TauriSnapshotTransport,
  type NativeMenuEvent,
  type NativeSuspensionEnvelope,
  type NativeSuspensionEvent,
  type NativeSuspensionReason,
  type PreferencesEnvelope,
  type ShellCapabilities,
  type ShellPreferences,
} from './tauriBridge'
import type { VisualStateV1 } from './visualStateContract'

const stageElement = ref<HTMLElement | null>(null)
const settingsOpen = ref(false)
const settingsBusy = ref(false)
const settingsError = ref('')
const shellWarning = ref('')
const preferences = ref<ShellPreferences | null>(null)
const settingsDraft = ref<ShellPreferences | null>(null)
const capabilities = ref<ShellCapabilities | null>(null)
const observationGeneration = ref(1)
const snapshot = ref<VisualStateV1 | null>(null)
const connection = ref<ObservationConnectionState>({
  health: 'idle',
  generation: 1,
  failure_count: 0,
})
const stageState = ref<SpiritStageState | null>(null)

let stage: SpiritStage | null = null
let client: VisualSnapshotClient | null = null
let cleanup: Array<() => void> = []
let disposed = false
let nativeSuspensionUnlisten: (() => void) | null = null
let nativeSuspensionConnect: Promise<boolean> | null = null
const suspensionReasons = new Set<ObservationSuspensionReason>()
const nativeSuspensionReasons: readonly NativeSuspensionReason[] = [
  'screen-locked',
  'session-inactive',
  'sleep',
  'system-hidden',
]
let nativeSuspensionRevision = 0

const ACTION_LABELS: Readonly<Record<string, string>> = {
  change_outfit: '换装',
  compose: '创作',
  draw: '绘画',
  eat: '用餐',
  explore_place: '探索',
  makeup: '化妆',
  pack_bag: '收拾行囊',
  prepare_food: '准备食物',
  remove_makeup: '卸妆',
  ride: '乘车',
  send: '发送消息',
  sleep: '休息',
  walk: '散步',
  settle: '安定下来',
}

const sourceLabel = computed(() => {
  const value = preferences.value
  if (value === null) return 'Local'
  return value.active_source === 'local' ? value.local.label : (value.remote?.label ?? 'Remote')
})

const statusTitle = computed(() => {
  const current = snapshot.value
  if (current?.status === 'ready') {
    return current.action === null ? '静静待着' : (ACTION_LABELS[current.action.name] ?? current.action.name)
  }
  if (current?.status === 'empty') return '尚无状态'
  if (connection.value.health === 'connecting') return '正在连接'
  if (connection.value.health === 'retrying') return '连接中断'
  if (connection.value.health === 'suspended') return '已暂停观察'
  return '等待 Kindred'
})

const statusDetail = computed(() => {
  const diagnostic = connection.value.diagnostic
  if (diagnostic === 'schema_mismatch') return '服务版本不兼容'
  if (diagnostic === 'invalid_payload') return '服务返回了无效状态'
  if (diagnostic === 'source_regression') return '来源状态发生回退'
  if (diagnostic === 'snapshot_conflict') return '同一 revision 内容冲突'
  if (diagnostic === 'transport_error') return '将自动重试，也可立即重试'
  if (shellWarning.value !== '') return shellWarning.value
  const current = snapshot.value
  if (current?.status === 'ready') return `${sourceLabel.value} · revision ${current.revision}`
  return sourceLabel.value
})

function setSuspended(reason: ObservationSuspensionReason, suspended: boolean): void {
  client?.setSuspended(reason, suspended)
  if (suspended) suspensionReasons.add(reason)
  else suspensionReasons.delete(reason)
  stage?.setSuspended(suspensionReasons.size > 0)
}

function clonePreferences(value: ShellPreferences): ShellPreferences {
  return JSON.parse(JSON.stringify(value)) as ShellPreferences
}

function applyPreferencesEnvelope(envelope: PreferencesEnvelope): void {
  preferences.value = clonePreferences(envelope.preferences)
  observationGeneration.value = envelope.observation_generation
  capabilities.value = envelope.capabilities
}

async function refreshPreferences(openDraft: boolean): Promise<void> {
  if (settingsBusy.value) return
  settingsBusy.value = true
  settingsError.value = ''
  try {
    const loaded = await loadPreferences()
    applyPreferencesEnvelope(loaded)
    if (openDraft || settingsOpen.value) settingsDraft.value = clonePreferences(loaded.preferences)
  } catch (error) {
    settingsError.value = error instanceof Error ? error.message : String(error)
    if (preferences.value === null) {
      settingsOpen.value = true
      settingsDraft.value = null
    }
  } finally {
    settingsBusy.value = false
  }
}

function openSettings(): void {
  settingsOpen.value = true
  if (settingsBusy.value) return
  settingsError.value = ''
  settingsDraft.value = preferences.value === null ? null : clonePreferences(preferences.value)
  if (settingsDraft.value === null) void refreshPreferences(true)
}

function closeSettings(): void {
  if (settingsBusy.value) return
  settingsOpen.value = false
  settingsDraft.value = null
  settingsError.value = ''
}

async function commitPreferences(): Promise<void> {
  const value = settingsDraft.value
  if (value === null || settingsBusy.value) return
  settingsBusy.value = true
  settingsError.value = ''
  try {
    const saved = await savePreferences(clonePreferences(value))
    const sourceChanged = saved.observation_generation !== observationGeneration.value
    applyPreferencesEnvelope(saved)
    if (sourceChanged) {
      snapshot.value = null
      client?.changeSource(new TauriSnapshotTransport())
    }
    settingsOpen.value = false
    settingsDraft.value = null
  } catch (error) {
    settingsError.value = error instanceof Error ? error.message : String(error)
  } finally {
    settingsBusy.value = false
  }
}

function retry(): void {
  if (suspensionReasons.has('native-lifecycle-unavailable')) {
    void connectNativeSuspension()
    return
  }
  client?.retryNow()
}

async function openCurrentKindred(): Promise<void> {
  settingsError.value = ''
  try {
    await openKindred(observationGeneration.value)
  } catch (error) {
    settingsError.value = error instanceof Error ? error.message : String(error)
    settingsOpen.value = true
  }
}

function handleMenu(event: NativeMenuEvent): void {
  if (event.error !== undefined) {
    settingsError.value = event.error
    settingsOpen.value = true
    if (settingsDraft.value === null && preferences.value !== null) {
      settingsDraft.value = clonePreferences(preferences.value)
    }
  }
  if (event.command === 'settings') openSettings()
  else if (event.command === 'always-on-top' && event.always_on_top !== undefined) {
    if (preferences.value !== null) preferences.value.always_on_top = event.always_on_top
    if (settingsDraft.value !== null) settingsDraft.value.always_on_top = event.always_on_top
  }
  else if (event.command === 'retry') retry()
}

function handleNativeSuspension(event: NativeSuspensionEvent): void {
  if (event.revision <= nativeSuspensionRevision) return
  nativeSuspensionRevision = event.revision
  setSuspended(event.reason, event.suspended)
}

function applyNativeSuspensionEnvelope(envelope: NativeSuspensionEnvelope): void {
  if (envelope.revision < nativeSuspensionRevision) return
  nativeSuspensionRevision = envelope.revision
  const active = new Set(envelope.active_reasons)
  for (const reason of nativeSuspensionReasons) setSuspended(reason, active.has(reason))
}

function openMenu(): void {
  void showContextMenu().catch((error: unknown) => {
    if (disposed) return
    shellWarning.value = `原生菜单不可用：${error instanceof Error ? error.message : String(error)}`
  })
}

function retainCleanup(dispose: () => void): boolean {
  if (disposed) {
    dispose()
    return false
  }
  cleanup.push(dispose)
  return true
}

function reportNativeSuspensionFailure(error: unknown): void {
  if (disposed) return
  setSuspended('native-lifecycle-unavailable', true)
  shellWarning.value = `系统暂停监听不可用：${error instanceof Error ? error.message : String(error)}`
  settingsOpen.value = true
}

async function synchronizeNativeSuspension(): Promise<boolean> {
  try {
    const envelope = await getNativeSuspensions()
    if (disposed) return false
    applyNativeSuspensionEnvelope(envelope)
    setSuspended('native-lifecycle-unavailable', false)
    if (shellWarning.value.startsWith('系统暂停监听不可用：')) shellWarning.value = ''
    return true
  } catch (error) {
    reportNativeSuspensionFailure(error)
    return false
  }
}

async function connectNativeSuspension(): Promise<boolean> {
  if (nativeSuspensionConnect !== null) return nativeSuspensionConnect
  setSuspended('native-lifecycle-unavailable', true)

  const attempt = (async () => {
    try {
      if (nativeSuspensionUnlisten === null) {
        const unlisten = await listenForSuspension(handleNativeSuspension)
        if (disposed) {
          unlisten()
          return false
        }
        let listenerDisposed = false
        const disposeListener = () => {
          if (listenerDisposed) return
          listenerDisposed = true
          unlisten()
          if (nativeSuspensionUnlisten === disposeListener) nativeSuspensionUnlisten = null
        }
        if (!retainCleanup(disposeListener)) return false
        nativeSuspensionUnlisten = disposeListener
      }
      return synchronizeNativeSuspension()
    } catch (error) {
      reportNativeSuspensionFailure(error)
      return false
    }
  })()
  nativeSuspensionConnect = attempt
  try {
    return await attempt
  } finally {
    if (nativeSuspensionConnect === attempt) nativeSuspensionConnect = null
  }
}

function ignoreResidentPointerReaction(event: Event): void {
  event.preventDefault()
}

onMounted(async () => {
  const root = stageElement.value
  if (root === null) return
  const pack = resolveBundledVisualPack()
  const loader = new BrowserVisualResourceLoader(pack.resolveSource, pack.resolveFrameManifest)
  stage = new SpiritStage({
    manifest: pack.manifest,
    rendererSessions: new DefaultRendererSessionFactory(
      new DefaultRendererAdapterFactory(loader, new DomVisualSurface(root)),
    ),
    observer: { onState: (state) => (stageState.value = state) },
  })
  client = new VisualSnapshotClient({
    transport: new TauriSnapshotTransport(),
    observer: {
      onSnapshot(value, context) {
        snapshot.value = value
        stage?.onSnapshot(value, context)
      },
      onConnection(state) {
        connection.value = state
        stage?.onConnection(state)
      },
    },
  })
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  const applyReducedMotion = () => stage?.setReducedMotion(reducedMotion.matches)
  applyReducedMotion()
  reducedMotion.addEventListener('change', applyReducedMotion)
  cleanup.push(() => reducedMotion.removeEventListener('change', applyReducedMotion))

  const applyVisibility = () => setSuspended('page-hidden', document.visibilityState !== 'visible')
  applyVisibility()
  document.addEventListener('visibilitychange', applyVisibility)
  cleanup.push(() => document.removeEventListener('visibilitychange', applyVisibility))

  await connectNativeSuspension()
  if (disposed) return
  try {
    const unlistenMenu = await listenForMenu(handleMenu)
    if (!retainCleanup(unlistenMenu)) return
  } catch (error) {
    if (disposed) return
    shellWarning.value = `原生菜单监听不可用：${error instanceof Error ? error.message : String(error)}`
  }
  try {
    await stage.initialize()
  } catch (error) {
    if (disposed) return
    shellWarning.value = `角色渲染初始化失败：${error instanceof Error ? error.message : String(error)}`
  }
  if (disposed) return
  await refreshPreferences(false)
  if (disposed) return
  client.start()
})

onBeforeUnmount(() => {
  disposed = true
  cleanup.forEach((dispose) => dispose())
  cleanup = []
  client?.stop()
  stage?.dispose()
})
</script>

<template>
  <main
    class="desktop-spirit-shell"
    aria-label="Kindred 桌面精灵"
    @contextmenu.prevent="openMenu"
  >
    <div class="drag-region" data-tauri-drag-region aria-label="拖动窗口" />
    <section
      ref="stageElement"
      class="spirit-stage"
      aria-live="polite"
      :aria-label="`${statusTitle}；${statusDetail}`"
      @click="ignoreResidentPointerReaction"
      @dblclick="ignoreResidentPointerReaction"
    />
    <section class="status-card" aria-live="polite">
      <span class="status-light" :data-health="connection.health" />
      <span class="status-copy">
        <strong>{{ statusTitle }}</strong>
        <small>{{ statusDetail }}</small>
      </span>
    </section>

    <section
      v-if="settingsOpen"
      class="settings-panel"
      role="dialog"
      aria-modal="true"
      aria-label="Kindred 设置"
      @contextmenu.stop
    >
      <header>
        <div>
          <strong>观察来源</strong>
          <small>只读取固定的 /api/visual-state</small>
        </div>
        <button type="button" aria-label="关闭设置" :disabled="settingsBusy" @click="closeSettings">×</button>
      </header>

      <fieldset v-if="settingsDraft" class="settings-fields" :disabled="settingsBusy" :aria-busy="settingsBusy">
        <p v-if="capabilities && !capabilities.transparent_window" class="settings-note">
          当前环境不支持透明窗口，已自动使用普通小窗口。
        </p>
        <p v-if="shellWarning" class="settings-error">{{ shellWarning }}</p>

        <label class="shell-choice">
          <input v-model="settingsDraft.always_on_top" type="checkbox" />
          <span>
            <strong>保持在最前</strong>
            <small>显示在普通应用窗口之上</small>
          </span>
        </label>

        <label class="source-choice">
          <input v-model="settingsDraft.active_source" type="radio" value="local" />
          <span>Local</span>
        </label>
        <label>
          <span>名称</span>
          <input v-model="settingsDraft.local.label" autocomplete="off" maxlength="80" />
        </label>
        <label>
          <span>地址</span>
          <input v-model="settingsDraft.local.base_url" autocomplete="off" spellcheck="false" />
        </label>

        <label class="source-choice">
          <input v-model="settingsDraft.active_source" type="radio" value="remote" />
          <span>Remote</span>
        </label>
        <label>
          <span>名称</span>
          <input
            :value="settingsDraft.remote?.label ?? ''"
            autocomplete="off"
            maxlength="80"
            placeholder="Ubuntu"
            @input="settingsDraft.remote = { label: ($event.target as HTMLInputElement).value, base_url: settingsDraft.remote?.base_url ?? '' }"
          />
        </label>
        <label>
          <span>地址</span>
          <input
            :value="settingsDraft.remote?.base_url ?? ''"
            autocomplete="off"
            spellcheck="false"
            placeholder="https://kindred.example"
            @input="settingsDraft.remote = { label: settingsDraft.remote?.label ?? 'Remote', base_url: ($event.target as HTMLInputElement).value }"
          />
        </label>

        <p v-if="settingsError" class="settings-error">{{ settingsError }}</p>
        <footer>
          <button type="button" @click="retry">立即重试</button>
          <button type="button" @click="openCurrentKindred">浏览器打开</button>
          <button class="primary" type="button" :disabled="settingsBusy" @click="commitPreferences">
            {{ settingsBusy ? '保存中…' : '保存' }}
          </button>
        </footer>
      </fieldset>
      <template v-else>
        <p class="settings-error">{{ settingsError || '偏好尚未载入' }}</p>
        <footer>
          <button class="primary" type="button" :disabled="settingsBusy" @click="refreshPreferences(true)">
            {{ settingsBusy ? '重新载入中…' : '重新载入' }}
          </button>
        </footer>
      </template>
    </section>
  </main>
</template>
