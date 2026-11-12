// HexWorld adapter. Upstream state and native schema remain authoritative.
import { useEffect, useRef } from 'react';
import type { DungeonProject } from './types/map';
import { encodeProject, decodeProject } from './utils/projectSchema';
import { createDefaultProject } from './hooks/mapStateUtils';
import { exportHighResPNG } from './utils/export';

declare global {
  interface Window {
    hexworld?: {
      ready: boolean;
      getProject: () => string;
      loadProject: (source: string | null) => Promise<void>;
      exportPNG: () => Promise<void>;
    };
  }
}

export function useHexWorld(project: DungeonProject, activeLevelIndex: number,
  phase: string, load: (project: DungeonProject) => boolean) {
  const latest = useRef({ project, activeLevelIndex, phase, load });
  latest.current = { project, activeLevelIndex, phase, load };
  useEffect(() => {
    if (!new URLSearchParams(location.search).has('hexworld')) return;
    window.hexworld = {
      get ready() { return ['saved', 'unsaved', 'restore-failed'].includes(latest.current.phase); },
      getProject() {
        const { project, activeLevelIndex } = latest.current;
        return JSON.stringify(encodeProject({ ...project, activeLevelIndex }));
      },
      async loadProject(source) {
        const next = source === null ? createDefaultProject() : decodeProject(JSON.parse(source));
        // A server save can finish before upstream's debounced device save.
        // Wait for the existing replacement guard rather than racing it.
        const readyBy = Date.now() + 10000;
        while (!['saved', 'unsaved', 'restore-failed'].includes(latest.current.phase)) {
          if (Date.now() > readyBy) throw new Error('Device save is blocked. Download your work, then retry importing.');
          await new Promise(resolve => setTimeout(resolve, 25));
        }
        const before = latest.current.project;
        if (!latest.current.load(next)) throw new Error('Editor is busy. Wait for its local save and retry.');
        // Wait for React to commit the replacement before allowing a server save.
        await new Promise<void>((resolve, reject) => {
          const started = Date.now();
          const check = () => {
            if (latest.current.project !== before && latest.current.phase !== 'restoring') resolve();
            else if (Date.now() - started > 10000) reject(new Error('Editor replacement timed out.'));
            else setTimeout(check, 20);
          };
          setTimeout(check, 20);
        });
      },
      async exportPNG() {
        const { project, activeLevelIndex } = latest.current;
        const map = project.levels[activeLevelIndex];
        await exportHighResPNG(map, { dpi: 72, pagePresetId: 'none', printMode: false,
          themeId: map.meta.theme || 'dungeon', viewMode: 'gm',
          customThemes: project.customThemes, customStamps: project.customStamps });
      },
    };
    return () => { delete window.hexworld; };
    // The bridge reads current state through a ref, without changing editor dispatch.
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
