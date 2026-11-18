#!/usr/bin/env python3
"""Build a read-only experiment pair from an existing one-layer ORA."""

import argparse
import hashlib
import io
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def build(blank, directory, layers, *, compact_layers=0, compact_size=5400):
    if not 2 <= layers <= 64:
        raise ValueError('choose between 2 and 64 prepared layers')
    if not 0<=compact_layers<layers or not 1<=compact_size<9000:
        raise ValueError('compact layers must leave a full-size top layer')
    with zipfile.ZipFile(blank) as source:
        if source.read('mimetype') != b'image/openraster':
            raise ValueError('expected OpenRaster input')
        image = ET.fromstring(source.read('stack.xml'))
        original = image.findall('.//layer')
        if len(original) != 1 or (image.attrib['w'], image.attrib['h']) != ('9000', '9000'):
            raise ValueError('expected the 9000 × 9000 single-layer ORA')
        png = source.read(original[0].attrib['src'])
        thumbnail = source.read('Thumbnails/thumbnail.png')
    compact_png=png
    if compact_layers:
        from PIL import Image
        with Image.open(io.BytesIO(png)) as source:
            with source.resize((compact_size,compact_size),Image.Resampling.NEAREST) as small:
                with io.BytesIO() as stream:
                    small.save(stream,format='PNG',compress_level=1)
                    compact_png=stream.getvalue()

    directory.mkdir(parents=True, exist_ok=False)
    light = directory / 'light_9000.ora'
    shutil.copyfile(blank, light)
    high = directory / f'layered_9000_{layers:02d}.ora'
    image = ET.Element('image', w='9000', h='9000', version='0.0.3')
    stack = ET.SubElement(image, 'stack')
    with zipfile.ZipFile(high, 'x') as output:
        output.writestr(zipfile.ZipInfo('mimetype'), b'image/openraster')
        for number in range(layers):
            member = f'data/layer_{number:02d}.png'
            ET.SubElement(stack, 'layer', {
                'name': f'Layer {number + 1}', 'src': member, 'x': '0', 'y': '0',
                'opacity': '1.0', 'visibility': 'visible' if number == 0 else 'hidden',
                'composite-op': 'svg:src-over',
            })
            output.writestr(zipfile.ZipInfo(member), compact_png if number>=layers-compact_layers else png)
        output.writestr(zipfile.ZipInfo('stack.xml'), ET.tostring(image, encoding='utf-8'))
        output.writestr(zipfile.ZipInfo('mergedimage.png'), png)
        output.writestr(zipfile.ZipInfo('Thumbnails/thumbnail.png'), thumbnail)
    return {
        name: dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   width=9000, height=9000, layers=count)
        for name, path, count in (('asset', light, 1), ('prepared_document', high, layers))
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('blank', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--layers', type=int, required=True)
    parser.add_argument('--compact-layers',type=int,default=0)
    parser.add_argument('--compact-size',type=int,default=5400)
    args = parser.parse_args()
    print(json.dumps(build(args.blank,args.directory,args.layers,compact_layers=args.compact_layers,
                           compact_size=args.compact_size),indent=2))


if __name__ == '__main__':
    main()
