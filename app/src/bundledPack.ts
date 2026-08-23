import rawManifest from '../../visual-packs/kindred-default/manifest.json'
import { validateVisualPackManifest, type VisualPackManifestV1 } from './visualPack'

const assetUrls = import.meta.glob(
  '../../visual-packs/kindred-default/assets/**/*.{png,webp,svg}',
  { eager: true, query: '?url', import: 'default' },
) as Readonly<Record<string, string>>

const frameManifests = import.meta.glob(
  '../../visual-packs/kindred-default/motions/*.json',
  { eager: true, import: 'default' },
) as Readonly<Record<string, unknown>>

const PACK_PREFIX = '../../visual-packs/kindred-default/'

export interface BundledVisualPack {
  manifest: VisualPackManifestV1
  resolveSource(source: string): string
  resolveFrameManifest(source: string): unknown
}

export function resolveBundledVisualPack(): BundledVisualPack {
  const manifest = validateVisualPackManifest(rawManifest)
  return {
    manifest,
    resolveSource(source: string): string {
      const url = assetUrls[`${PACK_PREFIX}${source}`]
      if (url === undefined) throw new Error(`BundledVisualAssetMissing:${source}`)
      return url
    },
    resolveFrameManifest(source: string): unknown {
      const manifest = frameManifests[`${PACK_PREFIX}${source}`]
      if (manifest === undefined) throw new Error(`BundledVisualAssetMissing:${source}`)
      return manifest
    },
  }
}
