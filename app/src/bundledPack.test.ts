import rawFrames from '../../visual-packs/kindred-default/motions/breathe.json'
import eatFrames from '../../visual-packs/kindred-default/motions/eat.json'
import settleFrames from '../../visual-packs/kindred-default/motions/settle.json'
import sleepFrames from '../../visual-packs/kindred-default/motions/sleep.json'
import { describe, expect, it } from 'vitest'
import { resolveBundledVisualPack } from './bundledPack'
import type { VisualAssetDescriptorV1 } from './visualPack'

function declaredAssets(): VisualAssetDescriptorV1[] {
  const { manifest } = resolveBundledVisualPack()
  return Object.values(manifest.motions).flatMap((motion) => [
    motion,
    ...(motion.decoration === undefined ? [] : [motion.decoration]),
    ...(motion.reduced_motion === undefined
      ? []
      : [
          motion.reduced_motion,
          ...(motion.reduced_motion.decoration === undefined
            ? []
            : [motion.reduced_motion.decoration]),
        ]),
  ])
}

describe('bundled desktop visual pack', () => {
  it('resolves every manifest and frame source from packaged assets', () => {
    const pack = resolveBundledVisualPack()
    const frameSources = [rawFrames, eatFrames, settleFrames, sleepFrames].flatMap((frames) => [
      ...frames.enter,
      ...frames.loop,
    ])

    for (const descriptor of declaredAssets()) {
      const resolved =
        descriptor.renderer === 'frames'
          ? pack.resolveFrameManifest(descriptor.source)
          : pack.resolveSource(descriptor.source)
      expect(resolved, descriptor.source).toBeTruthy()
    }
    for (const source of new Set(frameSources)) {
      expect(pack.resolveSource(source), source).toBeTruthy()
    }
  })

  it('ships action-specific body motion for the FRAME1 vertical slice', () => {
    const { manifest } = resolveBundledVisualPack()
    expect(manifest.motions[manifest.action_motions.settle]?.source).toBe('motions/settle.json')
    expect(manifest.motions[manifest.action_motions.sleep]?.source).toBe('motions/sleep.json')
    expect(manifest.motions[manifest.action_motions.eat]?.source).toBe('motions/eat.json')
    expect(manifest.motions[manifest.action_motions.draw]?.source).toBe('motions/draw.json')
  })

  it('fails closed when a pack source was not bundled', () => {
    const pack = resolveBundledVisualPack()
    expect(() => pack.resolveSource('https://example.invalid/remote.js')).toThrow(
      'BundledVisualAssetMissing',
    )
    expect(() => pack.resolveFrameManifest('https://example.invalid/remote.json')).toThrow(
      'BundledVisualAssetMissing',
    )
  })
})
