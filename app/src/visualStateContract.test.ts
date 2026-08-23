import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  validateVisualStateV1,
  VisualSnapshotValidationError,
  type VisualStateV1,
} from './visualStateContract'

interface ContractLock {
  schema: string
  kindred_private_repository: string
  kindred_private_commit: string
  kindred_public_repository: string
  kindred_public_commit: string
  sha256: string
  directory_sha256: string
}

const contractRoot = fileURLToPath(
  new URL('../../contracts/kindred/visual-state/', import.meta.url),
)
const lockPath = fileURLToPath(
  new URL('../../contracts/kindred/contract-lock.json', import.meta.url),
)

function sha256(value: string | Buffer): string {
  return createHash('sha256').update(value).digest('hex')
}

function contractFiles(root: string): string[] {
  const files: string[] = []
  const visit = (directory: string) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) visit(path)
      else if (entry.isFile()) files.push(relative(root, path).replaceAll('\\', '/'))
    }
  }
  visit(root)
  return files.sort()
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf8')) as unknown
}

describe('vendored VisualStateV1 contract', () => {
  it('matches the immutable public projection lock without network access', () => {
    const lock = readJson(lockPath) as ContractLock
    expect(lock).toEqual({
      schema: 'visual-state/v1.schema.json',
      kindred_private_repository: 'https://github.com/skedup/kindred-private',
      kindred_private_commit: 'cb0f5721189978250e6a78be34ea904768ee1239',
      kindred_public_repository: 'https://github.com/skedup/kindred',
      kindred_public_commit: 'b7b025b15deba366b10c141a089052ae330180be',
      sha256: '4a156e48f7249357e4ad10c02591626c9516bd67a147c58d2a5c2b54f8279db2',
      directory_sha256: 'da6995648bcd91e4e6f41211c58d102f0d9afb68bcfd7f9131604143bb99cb32',
    })

    const schemaPath = join(contractRoot, 'v1.schema.json')
    expect(sha256(readFileSync(schemaPath))).toBe(lock.sha256)
    expect(readFileSync(join(contractRoot, 'v1.schema.sha256'), 'utf8')).toBe(
      `${lock.sha256}  v1.schema.json\n`,
    )

    const manifest = contractFiles(contractRoot)
      .map(
        (path) =>
          `${sha256(readFileSync(join(contractRoot, path)))}  contracts/visual-state/${path}\n`,
      )
      .join('')
    expect(sha256(manifest)).toBe(lock.directory_sha256)
  })

  it('accepts every canonical positive fixture', () => {
    const fixtures = contractFiles(join(contractRoot, 'fixtures')).filter((path) =>
      path.startsWith('valid-'),
    )
    expect(fixtures).toHaveLength(3)
    for (const fixture of fixtures) {
      const value = readJson(join(contractRoot, 'fixtures', fixture))
      expect(validateVisualStateV1(value)).toEqual(value as VisualStateV1)
    }
  })

  it('counts string limits by Unicode code points like JSON Schema', () => {
    const readyFixture = readJson(
      join(contractRoot, 'fixtures', 'valid-ready-no-action.json'),
    ) as VisualStateV1
    expect(
      validateVisualStateV1({ schema_version: 1, source_id: '😀'.repeat(128), status: 'empty' }),
    ).toEqual({ schema_version: 1, source_id: '😀'.repeat(128), status: 'empty' })
    expect(() =>
      validateVisualStateV1({ schema_version: 1, source_id: '😀'.repeat(129), status: 'empty' }),
    ).toThrow(VisualSnapshotValidationError)
    expect(
      validateVisualStateV1({ ...readyFixture, committed_at: '😀'.repeat(256) }),
    ).toEqual({ ...readyFixture, committed_at: '😀'.repeat(256) })
    expect(() =>
      validateVisualStateV1({ ...readyFixture, committed_at: '😀'.repeat(257) }),
    ).toThrow(VisualSnapshotValidationError)
  })

  it('rejects every canonical negative fixture and fails closed on unknown schema versions', () => {
    const fixtures = contractFiles(join(contractRoot, 'fixtures')).filter((path) =>
      path.startsWith('invalid-'),
    )
    expect(fixtures).toHaveLength(9)
    for (const fixture of fixtures) {
      const value = readJson(join(contractRoot, 'fixtures', fixture))
      try {
        validateVisualStateV1(value)
        expect.unreachable(`accepted invalid fixture: ${fixture}`)
      } catch (error) {
        expect(error).toBeInstanceOf(VisualSnapshotValidationError)
        expect((error as VisualSnapshotValidationError).code).toBe(
          fixture === 'invalid-schema-version.json' ? 'schema_mismatch' : 'invalid_payload',
        )
      }
    }
  })
})
