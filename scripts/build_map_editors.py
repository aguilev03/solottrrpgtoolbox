#!/usr/bin/env python3
"""Build pinned source archives locally; Node is not needed in production."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'gridmapper': ('4719813ff0e8d868828a6a86518950f52d4bbc61', '4d3bf2125c55bf503f6c0d4824c5fba9c3331811453f7f73734191fe1cd907f3'),
    'dungeon-mapper': ('42d8dc09f0bf3dfa6f1d6ca4ab2abc47602107e5', 'b28f802ea03713c94eec1351e63583d7bd2244ab5924af78bda093fa8769b41b'),
}


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'Upstream patch no longer applies uniquely: {path}')
    path.write_text(text.replace(old, new))


def main():
    sources = ROOT / 'build/editor-sources'
    output = ROOT / 'build/editors'
    for editor, (revision, checksum) in PINS.items():
        archive = ROOT / 'vendor' / f'{editor}-source.tar.gz'
        if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
            raise RuntimeError(f'Source checksum mismatch: {editor}')
        source = sources / f'{editor}-{revision}'
        if not source.exists():
            source.mkdir(parents=True)
            with tarfile.open(archive) as stream:
                stream.extractall(source, filter='data')
        target = output / editor
        target.mkdir(parents=True, exist_ok=True)
        if editor == 'gridmapper':
            shutil.copy2(source / 'gridmapper.svg', target)
            shutil.copy2(source / 'LICENSE.md', target)
        else:
            # Apply customizations to a separate copy; pinned extracted sources stay untouched.
            work = ROOT / 'build/dungeon-mapper-work'
            shutil.copytree(source, work, dirs_exist_ok=True)
            replace(work / 'vite.config.ts', "base: '/Dungeon-Mapper/'", "base: '/dungeon-mapper/app/'")
            manifest = work / 'public/manifest.webmanifest'
            manifest.write_text(manifest.read_text().replace('/Dungeon-Mapper/', '/dungeon-mapper/app/'))
            replace(work / 'src/App.tsx', "import './App.css';", "import { useHexWorld } from './hexworld';\nimport './App.css';")
            replace(work / 'src/App.tsx', '} = useMapState();', '} = useMapState();\n  useHexWorld(project, activeLevelIndex, saveState.phase, loadProjectData);')
            replace(work / 'src/App.tsx', "return !params.has('project') || params.get('view') === 'library';", "return !params.has('hexworld') && (!params.has('project') || params.get('view') === 'library');")
            replace(work / 'src/utils/storage.ts', "const DB_NAME = 'dungeon-mapper';", "const DB_NAME = 'hexworld-dungeon-mapper-' + (new URLSearchParams(location.search).get('hexworld') || 'standalone');")
            # No offline worker in authenticated HexWorld: private pages must not be cached.
            replace(work / 'src/components/OfflineStatus.tsx', "if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return;", "if (new URLSearchParams(location.search).has('hexworld') || !import.meta.env.PROD || !('serviceWorker' in navigator)) return;")
            replace(work / 'src/components/OfflineStatus.tsx', 'if (!import.meta.env.PROD) return null;', "if (new URLSearchParams(location.search).has('hexworld') || !import.meta.env.PROD) return null;")
            shutil.copy2(ROOT / 'integrations/dungeon-bridge.ts', work / 'src/hexworld.ts')
            # Upstream has mirror tarball URLs for some public npm packages.
            # Use the standard registry while preserving pinned versions/integrities.
            lockfile = work / 'package-lock.json'
            lock = lockfile.read_text().replace('https://ms-feed-25.pkgs.visualstudio.com/1es-public/_packaging/npm-public/npm/registry/', 'https://registry.npmjs.org/')
            lockfile.write_text(lock)
            subprocess.run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=work, check=True)
            subprocess.run(['npm', 'run', 'build'], cwd=work, check=True)
            # Remove only this script's generated output, after a successful build,
            # so old hashed chunks cannot accumulate in release artifacts.
            shutil.rmtree(target)
            shutil.copytree(work / 'dist', target)
            shutil.copy2(source / 'LICENSE', target)
        (target / 'upstream.json').write_text(json.dumps({'editor': editor, 'revision': revision, 'sha256': checksum}, indent=2))
    print(f'Built editors in {output}')


if __name__ == '__main__':
    main()
