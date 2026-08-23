export type VisualRendererV1 = 'static' | 'frames'

export interface VisualAssetDescriptorV1 {
  renderer: VisualRendererV1
  source: string
}

export interface VisualReducedMotionV1 {
  renderer: 'static'
  source: string
  decoration?: VisualAssetDescriptorV1 & { renderer: 'static' }
}

export interface VisualMotionV1 extends VisualAssetDescriptorV1 {
  fallback_motion?: string
  decoration?: VisualAssetDescriptorV1
  reduced_motion: VisualReducedMotionV1
}

export interface VisualPackManifestV1 {
  schema_version: 1
  id: string
  identity: string
  fallback_motion: string
  action_motions: Readonly<Record<string, string>>
  motions: Readonly<Record<string, VisualMotionV1>>
}

export interface FrameManifestV1 {
  schema_version: 1
  fps: number
  enter: readonly string[]
  loop: readonly string[]
}

export type VisualResolutionDiagnostic =
  | 'no_action'
  | 'unknown_action'
  | 'motion_unavailable'
  | 'renderer_unavailable'

export interface ResolvedVisualMotionV1 {
  requested_action: string | null
  motion_key: string
  presentation: VisualAssetDescriptorV1
  decoration?: VisualAssetDescriptorV1
  used_fallback: boolean
  fallback_chain: readonly string[]
  diagnostic?: VisualResolutionDiagnostic
}

export interface ResolveVisualMotionOptions {
  reducedMotion?: boolean
  availableRenderers?: ReadonlySet<VisualRendererV1>
  unavailableMotionKeys?: ReadonlySet<string>
}

export class VisualPackValidationError extends Error {}

export class VisualPackResolutionError extends Error {}

const IDENTIFIER = /^[a-z][a-z0-9-]{0,63}$/
const ACTION_IDENTIFIER = /^[a-z][a-z0-9_]{0,63}$/
const STATIC_EXTENSIONS = new Set(['.png', '.webp', '.svg'])
const SAFE_SOURCE = /^[A-Za-z0-9][A-Za-z0-9._/-]*$/
const MAX_FRAME_COUNT = 600
const MAX_FPS = 30

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new VisualPackValidationError(`${label} must be an object`)
  return value
}

function exactKeys(value: Record<string, unknown>, allowed: readonly string[], label: string) {
  const allowedSet = new Set(allowed)
  const unexpected = Object.keys(value).filter((key) => !allowedSet.has(key))
  if (unexpected.length > 0) {
    throw new VisualPackValidationError(`${label} has unsupported key: ${unexpected.sort()[0]}`)
  }
}

function integer(value: unknown, label: string, minimum: number, maximum: number): number {
  if (!Number.isInteger(value) || typeof value !== 'number' || value < minimum || value > maximum) {
    throw new VisualPackValidationError(`${label} must be an integer in ${minimum}..${maximum}`)
  }
  return value
}

function identifier(value: unknown, label: string, action = false): string {
  const pattern = action ? ACTION_IDENTIFIER : IDENTIFIER
  if (typeof value !== 'string' || !pattern.test(value)) {
    throw new VisualPackValidationError(`${label} is not a valid identifier`)
  }
  return value
}

function extension(path: string): string {
  const index = path.lastIndexOf('.')
  return index < 0 ? '' : path.slice(index).toLowerCase()
}

export function validatePackRelativeSource(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new VisualPackValidationError(`${label} must be a non-empty path`)
  }
  if (
    value.startsWith('/') ||
    !SAFE_SOURCE.test(value) ||
    value.includes('\\') ||
    value.includes('?') ||
    value.includes('#') ||
    value.includes('://')
  ) {
    throw new VisualPackValidationError(`${label} must be a local pack-relative path`)
  }
  const segments = value.split('/')
  if (segments.some((part) => part === '' || part === '.' || part === '..')) {
    throw new VisualPackValidationError(`${label} contains an unsafe path segment`)
  }
  return value
}

function assetDescriptor(
  value: unknown,
  label: string,
  options: { staticOnly?: boolean } = {},
): VisualAssetDescriptorV1 {
  const raw = record(value, label)
  exactKeys(raw, ['renderer', 'source'], label)
  const renderer = raw.renderer
  if (renderer !== 'static' && renderer !== 'frames') {
    throw new VisualPackValidationError(`${label}.renderer is unsupported`)
  }
  if (options.staticOnly && renderer !== 'static') {
    throw new VisualPackValidationError(`${label} must use the static renderer`)
  }
  const source = validatePackRelativeSource(raw.source, `${label}.source`)
  const suffix = extension(source)
  if (renderer === 'frames' && suffix !== '.json') {
    throw new VisualPackValidationError(`${label}.source must be a frame manifest`)
  }
  if (renderer === 'static' && !STATIC_EXTENSIONS.has(suffix)) {
    throw new VisualPackValidationError(`${label}.source must be a supported static asset`)
  }
  return { renderer, source }
}

function reducedMotion(value: unknown, label: string): VisualReducedMotionV1 {
  const raw = record(value, label)
  exactKeys(raw, ['renderer', 'source', 'decoration'], label)
  const body = assetDescriptor(
    { renderer: raw.renderer, source: raw.source },
    label,
    { staticOnly: true },
  )
  const decoration =
    raw.decoration === undefined
      ? undefined
      : assetDescriptor(raw.decoration, `${label}.decoration`, { staticOnly: true })
  return {
    renderer: 'static',
    source: body.source,
    ...(decoration === undefined
      ? {}
      : { decoration: { renderer: 'static', source: decoration.source } }),
  }
}

function motion(value: unknown, label: string): VisualMotionV1 {
  const raw = record(value, label)
  exactKeys(
    raw,
    ['renderer', 'source', 'fallback_motion', 'decoration', 'reduced_motion'],
    label,
  )
  const body = assetDescriptor({ renderer: raw.renderer, source: raw.source }, label)
  const fallbackMotion =
    raw.fallback_motion === undefined
      ? undefined
      : identifier(raw.fallback_motion, `${label}.fallback_motion`)
  const decoration =
    raw.decoration === undefined
      ? undefined
      : assetDescriptor(raw.decoration, `${label}.decoration`)
  return {
    ...body,
    ...(fallbackMotion === undefined ? {} : { fallback_motion: fallbackMotion }),
    ...(decoration === undefined ? {} : { decoration }),
    reduced_motion: reducedMotion(raw.reduced_motion, `${label}.reduced_motion`),
  }
}

function validateFallbackChains(manifest: VisualPackManifestV1): void {
  const states = new Map<string, 'visiting' | 'visited'>()
  const visit = (motionKey: string): void => {
    const state = states.get(motionKey)
    if (state === 'visiting') throw new VisualPackValidationError('motion fallback cycle detected')
    if (state === 'visited') return
    states.set(motionKey, 'visiting')
    const current = manifest.motions[motionKey]
    if (current === undefined) throw new VisualPackValidationError('motion fallback is undefined')
    const next =
      current.fallback_motion ??
      (motionKey === manifest.fallback_motion ? undefined : manifest.fallback_motion)
    if (next !== undefined) visit(next)
    states.set(motionKey, 'visited')
  }
  Object.keys(manifest.motions).forEach(visit)
}

export function validateVisualPackManifest(value: unknown): VisualPackManifestV1 {
  const raw = record(value, 'visual pack')
  exactKeys(
    raw,
    ['schema_version', 'id', 'identity', 'fallback_motion', 'action_motions', 'motions'],
    'visual pack',
  )
  if (raw.schema_version !== 1) {
    throw new VisualPackValidationError('visual pack schema_version is unsupported')
  }
  const id = identifier(raw.id, 'visual pack id')
  const identity = identifier(raw.identity, 'visual pack identity')
  const fallbackMotion = identifier(raw.fallback_motion, 'visual pack fallback_motion')
  const rawActionMotions = record(raw.action_motions, 'visual pack action_motions')
  const actionMotions = Object.create(null) as Record<string, string>
  for (const [action, motionKey] of Object.entries(rawActionMotions)) {
    actionMotions[identifier(action, `action ${action}`, true)] = identifier(
      motionKey,
      `action ${action} motion`,
    )
  }
  if (Object.keys(actionMotions).length === 0) {
    throw new VisualPackValidationError('visual pack action_motions must not be empty')
  }
  const rawMotions = record(raw.motions, 'visual pack motions')
  const motions = Object.create(null) as Record<string, VisualMotionV1>
  for (const [motionKey, definition] of Object.entries(rawMotions)) {
    const key = identifier(motionKey, `motion ${motionKey}`)
    motions[key] = motion(definition, `motion ${key}`)
  }
  const fallback = motions[fallbackMotion]
  if (
    fallback === undefined ||
    fallback.renderer !== 'static' ||
    (fallback.decoration !== undefined && fallback.decoration.renderer !== 'static')
  ) {
    throw new VisualPackValidationError('visual pack fallback must be a declared static motion')
  }
  for (const [action, motionKey] of Object.entries(actionMotions)) {
    if (motions[motionKey] === undefined) {
      throw new VisualPackValidationError(`action ${action} references an undefined motion`)
    }
  }
  const manifest: VisualPackManifestV1 = {
    schema_version: 1,
    id,
    identity,
    fallback_motion: fallbackMotion,
    action_motions: actionMotions,
    motions,
  }
  validateFallbackChains(manifest)
  return manifest
}

export function validateFrameManifest(value: unknown): FrameManifestV1 {
  const raw = record(value, 'frame manifest')
  exactKeys(raw, ['schema_version', 'fps', 'enter', 'loop'], 'frame manifest')
  if (raw.schema_version !== 1) {
    throw new VisualPackValidationError('frame manifest schema_version is unsupported')
  }
  const fps = integer(raw.fps, 'frame manifest fps', 1, MAX_FPS)
  const sequence = (candidate: unknown, label: string, allowEmpty: boolean): string[] => {
    if (!Array.isArray(candidate) || (!allowEmpty && candidate.length === 0)) {
      throw new VisualPackValidationError(`${label} must be a frame list`)
    }
    return candidate.map((source, index) => {
      const path = validatePackRelativeSource(source, `${label}[${index}]`)
      if (!STATIC_EXTENSIONS.has(extension(path))) {
        throw new VisualPackValidationError(`${label}[${index}] is not a static frame`)
      }
      return path
    })
  }
  const enter = sequence(raw.enter, 'frame manifest enter', true)
  const loop = sequence(raw.loop, 'frame manifest loop', false)
  if (enter.length + loop.length > MAX_FRAME_COUNT) {
    throw new VisualPackValidationError('frame manifest exceeds the frame limit')
  }
  return { schema_version: 1, fps, enter, loop }
}

function presentation(
  motionDefinition: VisualMotionV1,
  reduced: boolean,
): { body: VisualAssetDescriptorV1; decoration?: VisualAssetDescriptorV1 } {
  if (reduced) {
    const reducedDefinition = motionDefinition.reduced_motion
    return {
      body: { renderer: 'static', source: reducedDefinition.source },
      ...(reducedDefinition.decoration === undefined
        ? {}
        : { decoration: reducedDefinition.decoration }),
    }
  }
  return {
    body: { renderer: motionDefinition.renderer, source: motionDefinition.source },
    ...(motionDefinition.decoration === undefined
      ? {}
      : { decoration: motionDefinition.decoration }),
  }
}

export function resolveVisualMotion(
  manifest: VisualPackManifestV1,
  action: string | null,
  options: ResolveVisualMotionOptions = {},
): ResolvedVisualMotionV1 {
  const availableRenderers =
    options.availableRenderers ?? new Set<VisualRendererV1>(['static', 'frames'])
  const unavailableMotions = options.unavailableMotionKeys ?? new Set<string>()
  const mapped =
    action !== null && Object.hasOwn(manifest.action_motions, action)
      ? manifest.action_motions[action]
      : undefined
  const initial = mapped ?? manifest.fallback_motion
  let diagnostic: VisualResolutionDiagnostic | undefined =
    action === null ? 'no_action' : mapped === undefined ? 'unknown_action' : undefined
  const chain: string[] = []
  const seen = new Set<string>()
  let currentKey: string | undefined = initial

  while (currentKey !== undefined && !seen.has(currentKey)) {
    seen.add(currentKey)
    chain.push(currentKey)
    const current: VisualMotionV1 | undefined = manifest.motions[currentKey]
    if (current === undefined) break
    const selected = presentation(current, options.reducedMotion ?? false)
    const rendererReady =
      availableRenderers.has(selected.body.renderer) &&
      (selected.decoration === undefined || availableRenderers.has(selected.decoration.renderer))
    if (!unavailableMotions.has(currentKey) && rendererReady) {
      return {
        requested_action: action,
        motion_key: currentKey,
        presentation: selected.body,
        ...(selected.decoration === undefined ? {} : { decoration: selected.decoration }),
        used_fallback: currentKey !== initial || mapped === undefined,
        fallback_chain: chain,
        ...(diagnostic === undefined ? {} : { diagnostic }),
      }
    }
    diagnostic = unavailableMotions.has(currentKey)
      ? 'motion_unavailable'
      : 'renderer_unavailable'
    currentKey =
      current.fallback_motion ??
      (currentKey === manifest.fallback_motion ? undefined : manifest.fallback_motion)
  }
  throw new VisualPackResolutionError('visual pack has no renderable static fallback')
}

export function presentationSignature(
  manifest: VisualPackManifestV1,
  action: string,
  reducedMotion: boolean,
): string {
  const resolved = resolveVisualMotion(manifest, action, { reducedMotion })
  return [
    resolved.presentation.renderer,
    resolved.presentation.source,
    resolved.decoration?.renderer ?? '',
    resolved.decoration?.source ?? '',
  ].join('|')
}
