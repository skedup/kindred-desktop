// Desktop-owned runtime projection of the vendored contracts/kindred/visual-state capsule.
// Canonical fixtures keep this handwritten boundary aligned without codegen or runtime schema IO.
export interface VisualActionV1 {
  name: string
}

export interface VisualStateEmptyV1 {
  schema_version: 1
  source_id: string
  status: 'empty'
}

export interface VisualStateReadyV1 {
  schema_version: 1
  source_id: string
  status: 'ready'
  revision: number
  committed_at: string
  motion_instance_id: `tick:${number}`
  action: VisualActionV1 | null
}

export type VisualStateV1 = VisualStateEmptyV1 | VisualStateReadyV1

export class VisualSnapshotValidationError extends Error {
  constructor(
    message: string,
    readonly code: 'invalid_payload' | 'schema_mismatch' = 'invalid_payload',
  ) {
    super(message)
    this.name = 'VisualSnapshotValidationError'
  }
}

const ACTION_IDENTIFIER = /^[a-z][a-z0-9_]{0,63}$/
const MOTION_INSTANCE = /^tick:[1-9][0-9]*$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function exactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  label: string,
): void {
  const keys = Object.keys(value).sort()
  const wanted = [...expected].sort()
  if (keys.length !== wanted.length || keys.some((key, index) => key !== wanted[index])) {
    throw new VisualSnapshotValidationError(`${label} fields are invalid`)
  }
}

function nonEmptyString(value: unknown, label: string, maxLength = 256): string {
  if (typeof value !== 'string') {
    throw new VisualSnapshotValidationError(`${label} is invalid`)
  }
  const length = Array.from(value).length
  if (length === 0 || length > maxLength || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new VisualSnapshotValidationError(`${label} is invalid`)
  }
  return value
}

export function validateVisualStateV1(value: unknown): VisualStateV1 {
  if (!isRecord(value)) throw new VisualSnapshotValidationError('snapshot must be an object')
  if (value.schema_version !== 1) {
    throw new VisualSnapshotValidationError('snapshot schema is unsupported', 'schema_mismatch')
  }
  const sourceId = nonEmptyString(value.source_id, 'source_id', 128)
  if (value.status === 'empty') {
    exactKeys(value, ['schema_version', 'source_id', 'status'], 'empty snapshot')
    return { schema_version: 1, source_id: sourceId, status: 'empty' }
  }
  if (value.status !== 'ready') {
    throw new VisualSnapshotValidationError('snapshot status is unsupported')
  }
  exactKeys(
    value,
    [
      'schema_version',
      'source_id',
      'status',
      'revision',
      'committed_at',
      'motion_instance_id',
      'action',
    ],
    'ready snapshot',
  )
  if (
    typeof value.revision !== 'number' ||
    !Number.isSafeInteger(value.revision) ||
    value.revision < 1
  ) {
    throw new VisualSnapshotValidationError('snapshot revision is invalid')
  }
  const committedAt = nonEmptyString(value.committed_at, 'committed_at')
  const motionInstanceId = nonEmptyString(value.motion_instance_id, 'motion_instance_id', 64)
  if (!MOTION_INSTANCE.test(motionInstanceId)) {
    throw new VisualSnapshotValidationError('motion_instance_id is invalid')
  }
  let action: VisualActionV1 | null = null
  if (value.action !== null) {
    if (!isRecord(value.action)) {
      throw new VisualSnapshotValidationError('snapshot action is invalid')
    }
    exactKeys(value.action, ['name'], 'snapshot action')
    const name = nonEmptyString(value.action.name, 'action.name', 64)
    if (!ACTION_IDENTIFIER.test(name)) {
      throw new VisualSnapshotValidationError('action.name is invalid')
    }
    action = { name }
  }
  return {
    schema_version: 1,
    source_id: sourceId,
    status: 'ready',
    revision: value.revision,
    committed_at: committedAt,
    motion_instance_id: motionInstanceId as `tick:${number}`,
    action,
  }
}
