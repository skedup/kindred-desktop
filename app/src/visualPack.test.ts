import { describe, expect, it } from 'vitest'
import defaultFrameJson from '../../visual-packs/kindred-default/motions/breathe.json'
import defaultPackJson from '../../visual-packs/kindred-default/manifest.json'
import {
  presentationSignature,
  resolveVisualMotion,
  validateFrameManifest,
  validatePackRelativeSource,
  validateVisualPackManifest,
  VisualPackResolutionError,
  VisualPackValidationError,
} from './visualPack'

const BUILT_IN_ACTIONS = [
  'change_outfit',
  'compose',
  'draw',
  'eat',
  'explore_place',
  'makeup',
  'pack_bag',
  'prepare_food',
  'remove_makeup',
  'ride',
  'send',
  'sleep',
  'walk',
  'settle',
] as const

function simplePack() {
  return {
    schema_version: 1,
    id: 'fixture-pack',
    identity: 'fixture-resident',
    fallback_motion: 'neutral',
    action_motions: { walk: 'shared', ride: 'shared' },
    motions: {
      neutral: {
        renderer: 'static',
        source: 'neutral.png',
        fallback_motion: undefined as string | undefined,
        backdrop: undefined as { renderer: string; source: string } | undefined,
        decoration: undefined as { renderer: string; source: string } | undefined,
        reduced_motion: { renderer: 'static', source: 'neutral.png' },
      },
      shared: {
        renderer: 'frames',
        source: 'shared.json',
        fallback_motion: 'neutral',
        backdrop: undefined as { renderer: string; source: string } | undefined,
        reduced_motion: {
          renderer: 'static',
          source: 'neutral.png',
          backdrop: undefined as { renderer: string; source: string } | undefined,
        },
      },
    },
  }
}

describe('visual pack contract', () => {
  it('validates the bundled pack and covers every built-in action plus settle', () => {
    const manifest = validateVisualPackManifest(defaultPackJson)
    expect(Object.keys(manifest.action_motions).sort()).toEqual([...BUILT_IN_ACTIONS].sort())
    expect(validateFrameManifest(defaultFrameJson)).toEqual(defaultFrameJson)

    const normal = new Set(
      BUILT_IN_ACTIONS.map((action) => presentationSignature(manifest, action, false)),
    )
    const reduced = new Set(
      BUILT_IN_ACTIONS.map((action) => presentationSignature(manifest, action, true)),
    )
    expect(normal.size).toBe(BUILT_IN_ACTIONS.length)
    expect(reduced.size).toBe(BUILT_IN_ACTIONS.length)
  })

  it('allows many actions to intentionally share one motion', () => {
    const manifest = validateVisualPackManifest(simplePack())
    expect(resolveVisualMotion(manifest, 'walk').motion_key).toBe('shared')
    expect(resolveVisualMotion(manifest, 'ride').motion_key).toBe('shared')
  })

  it('resolves no action and unknown actions to the neutral fallback', () => {
    const manifest = validateVisualPackManifest(simplePack())
    expect(resolveVisualMotion(manifest, null)).toMatchObject({
      motion_key: 'neutral',
      used_fallback: true,
      diagnostic: 'no_action',
    })
    expect(resolveVisualMotion(manifest, 'future_action')).toMatchObject({
      motion_key: 'neutral',
      used_fallback: true,
      diagnostic: 'unknown_action',
    })
    expect(resolveVisualMotion(manifest, 'constructor')).toMatchObject({
      motion_key: 'neutral',
      diagnostic: 'unknown_action',
    })
  })

  it('falls back deterministically when a motion or renderer is unavailable', () => {
    const manifest = validateVisualPackManifest(simplePack())
    expect(
      resolveVisualMotion(manifest, 'walk', { unavailableMotionKeys: new Set(['shared']) }),
    ).toMatchObject({
      motion_key: 'neutral',
      fallback_chain: ['shared', 'neutral'],
      diagnostic: 'motion_unavailable',
    })
    expect(resolveVisualMotion(manifest, 'walk', { availableRenderers: new Set(['static']) }))
      .toMatchObject({
        motion_key: 'neutral',
        fallback_chain: ['shared', 'neutral'],
        diagnostic: 'renderer_unavailable',
      })
    expect(() =>
      resolveVisualMotion(manifest, 'walk', {
        availableRenderers: new Set(['static']),
        unavailableMotionKeys: new Set(['shared', 'neutral']),
      }),
    ).toThrow(VisualPackResolutionError)
  })

  it('uses the explicit reduced-motion presentation without inferring filenames', () => {
    const manifest = validateVisualPackManifest(defaultPackJson)
    const result = resolveVisualMotion(manifest, 'change_outfit', { reducedMotion: true })
    expect(result.presentation).toEqual({
      renderer: 'static',
      source: 'assets/body/neutral.png',
    })
    expect(result.decoration?.source).toBe('assets/decorations/change-outfit.png')
  })

  it('resolves a static backdrop behind both animated and reduced presentations', () => {
    const pack = simplePack()
    pack.motions.shared.backdrop = { renderer: 'static', source: 'night.png' }
    pack.motions.shared.reduced_motion.backdrop = {
      renderer: 'static',
      source: 'night.png',
    }
    const manifest = validateVisualPackManifest(pack)

    expect(resolveVisualMotion(manifest, 'walk')).toMatchObject({
      presentation: { renderer: 'frames', source: 'shared.json' },
      backdrop: { renderer: 'static', source: 'night.png' },
    })
    expect(resolveVisualMotion(manifest, 'walk', { reducedMotion: true })).toMatchObject({
      presentation: { renderer: 'static', source: 'neutral.png' },
      backdrop: { renderer: 'static', source: 'night.png' },
    })
  })

  it('rejects animated backdrops', () => {
    const pack = simplePack()
    pack.motions.shared.backdrop = { renderer: 'frames', source: 'night.json' }
    expect(() => validateVisualPackManifest(pack)).toThrow(/renderer/)
  })

  it('rejects fallback cycles and unsupported identity or audio fields', () => {
    const cycle = simplePack()
    cycle.motions.neutral.fallback_motion = 'shared'
    expect(() => validateVisualPackManifest(cycle)).toThrow(/fallback cycle/)

    expect(() =>
      validateVisualPackManifest({ ...simplePack(), identity_from_state: 'appearance' }),
    ).toThrow(VisualPackValidationError)
    expect(() => validateVisualPackManifest({ ...simplePack(), audio: 'idle.mp3' })).toThrow(
      VisualPackValidationError,
    )
  })

  it('requires the complete neutral fallback presentation to be static', () => {
    const pack = simplePack()
    pack.motions.neutral.decoration = { renderer: 'frames', source: 'sparkle.json' }
    expect(() => validateVisualPackManifest(pack)).toThrow(/static motion/)
  })

  it.each([
    '../outside.png',
    '/absolute.png',
    'https://example.com/a.png',
    'https:asset.png',
    '%2e%2e/outside.png',
    'a\\b.png',
    'a.png?x=1',
  ])(
    'rejects unsafe or non-local source %s',
    (source) => {
      expect(() => validatePackRelativeSource(source, 'fixture')).toThrow(
        VisualPackValidationError,
      )
    },
  )

  it('enforces frame-rate and frame-count limits', () => {
    expect(() =>
      validateFrameManifest({ schema_version: 1, fps: 31, enter: [], loop: ['frame.png'] }),
    ).toThrow(/fps/)
    expect(() =>
      validateFrameManifest({
        schema_version: 1,
        fps: 30,
        enter: [],
        loop: Array.from({ length: 601 }, () => 'frame.png'),
      }),
    ).toThrow(/frame limit/)
  })

  it('accepts bounded enter replay intervals and rejects incomplete schedules', () => {
    expect(
      validateFrameManifest({
        schema_version: 1,
        fps: 12,
        enter: ['event.png'],
        loop: ['idle.png'],
        replay_interval: { min_ms: 12_000, max_ms: 28_000 },
      }),
    ).toEqual({
      schema_version: 1,
      fps: 12,
      enter: ['event.png'],
      loop: ['idle.png'],
      replay_interval: { min_ms: 12_000, max_ms: 28_000 },
    })

    expect(() =>
      validateFrameManifest({
        schema_version: 1,
        fps: 12,
        enter: [],
        loop: ['idle.png'],
        replay_interval: { min_ms: 12_000, max_ms: 28_000 },
      }),
    ).toThrow(/requires enter/)
    expect(() =>
      validateFrameManifest({
        schema_version: 1,
        fps: 12,
        enter: ['event.png'],
        loop: ['idle.png'],
        replay_interval: { min_ms: 28_000, max_ms: 12_000 },
      }),
    ).toThrow(/must not be smaller/)
  })
})
