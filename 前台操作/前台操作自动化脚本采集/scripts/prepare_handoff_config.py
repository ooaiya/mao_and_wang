#!/usr/bin/env python3
"""Point a shipped PILOT template at the transferred ORA and PNG inputs."""

import argparse
import json
from pathlib import Path
import sys

GUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GUI))

from oomlab_krita_collect.common import fresh, save
from oomlab_krita_collect.pilot_assets import inventory


def relocated(original, assets_root):
    path = Path(original)
    parts = path.parts
    if 'OOM_assets' not in parts:
        raise ValueError(f'template path is outside OOM_assets: {original}')
    relative = parts[parts.index('OOM_assets') + 1:]
    if '..' in relative:
        raise ValueError(f'unsafe template path: {original}')
    return str(assets_root.joinpath(*relative))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    parser.add_argument('--template', type=Path, default=GUI/'configs/collection.rapid-9000-medium-tail-extended.json')
    parser.add_argument('--display-size', type=int, nargs=2, metavar=('WIDTH', 'HEIGHT'), required=True)
    args = parser.parse_args()

    config = json.loads(args.template.read_text(encoding='utf-8'))
    automation = config.get('automation', {})
    if (config.get('mode') != 'pilot' or min(args.display_size) <= 0
            or not automation.get('prepared_document') or not automation.get('tail_document')):
        parser.error('a low–high–medium template and positive display dimensions are required')
    asset_root = args.assets_root.absolute()
    config['display_size'] = args.display_size
    documents = [config['asset']]
    documents.extend(config['automation'][key] for key in ('prepared_document', 'tail_document')
                     if key in config['automation'])
    for document in documents:
        document['path'] = relocated(document['path'], asset_root)
    config['pilot']['layers_dir'] = relocated(config['pilot']['layers_dir'], asset_root)

    manifest = inventory(config)
    config['asset']['sha256'] = manifest['ora']['sha256']
    dest = fresh(args.output)
    save(dest/'foreground_config.json', config)
    save(dest/'foreground_assets.json', manifest)
    print(dest)


if __name__ == '__main__':
    main()
