// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'
import defaultFrameJson from '../../visual-packs/kindred-default/motions/breathe.json'
import defaultPackJson from '../../visual-packs/kindred-default/manifest.json'
import {
  DefaultRendererAdapterFactory,
  DefaultRendererSessionFactory,
  DomVisualSurface,
  type AnimationFrameClock,
  type VisualResourceLoader,
} from './renderAdapters'
import { SpiritStage } from './spiritStage'
import { validateVisualPackManifest } from './visualPack'

const stoppedClock: AnimationFrameClock = {
  now: () => 0,
  request: () => 1,
  cancel: () => {},
}

const resources: VisualResourceLoader = {
  loadImage: async (source) => `asset://${source}`,
  loadFrameManifest: async () => defaultFrameJson,
}

describe('bundled visual cue content review', () => {
  it('renders one silent non-text cue for every action in normal and reduced-motion modes', async () => {
    const manifest = validateVisualPackManifest(defaultPackJson)
    const modes = [false, true]
    const cueSources = new Map<boolean, Set<string>>(modes.map((mode) => [mode, new Set()]))

    for (const reduced of modes) {
      for (const [index, action] of Object.keys(manifest.action_motions).entries()) {
        const root = document.createElement('div')
        const stage = new SpiritStage({
          manifest,
          rendererSessions: new DefaultRendererSessionFactory(
            new DefaultRendererAdapterFactory(
              resources,
              new DomVisualSurface(root),
              stoppedClock,
            ),
          ),
          crossfadeMs: 0,
        })
        stage.setReducedMotion(reduced)
        stage.onSnapshot(
          {
            schema_version: 1,
            source_id: 'install:review',
            status: 'ready',
            revision: index + 1,
            committed_at: '2026-08-18T00:00:00Z',
            motion_instance_id: `tick:${index + 1}`,
            action: { name: action },
          },
          { generation: 1, reason: 'accepted' },
        )
        await stage.whenIdle()

        const images = [...root.querySelectorAll('img')]
        expect(images).toHaveLength(2)
        expect(root.querySelectorAll('audio, video')).toHaveLength(0)
        expect(images.every((image) => image.alt === '' && image.style.opacity === '1')).toBe(true)
        expect(root.textContent).toBe('')
        const cue = images.find((image) => image.dataset.visualLayer === 'decoration')
        expect(cue?.src).toContain(`/decorations/${action.replaceAll('_', '-')}.png`)
        cueSources.get(reduced)?.add(cue?.src ?? '')
        stage.dispose()
      }
      expect(cueSources.get(reduced)?.size).toBe(Object.keys(manifest.action_motions).length)
    }
  })
})
