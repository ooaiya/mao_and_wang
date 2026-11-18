import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from .common import fingerprint


def inspect(path,verify_zip=False):
    before=fingerprint(path)
    with zipfile.ZipFile(path) as z:
        if z.getinfo('mimetype').file_size>128:raise ValueError('oversized mimetype')
        if z.read('mimetype')!=b'image/openraster': raise ValueError('not OpenRaster')
        info=z.getinfo('stack.xml')
        if info.file_size>8*1024**2: raise ValueError('oversized stack.xml')
        xml=z.read(info)
        if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml: raise ValueError('unsafe XML declarations')
        if verify_zip and z.testzip() is not None:raise ValueError('corrupt ORA ZIP member')
        image=ET.fromstring(xml)
        result=dict(width=int(image.attrib['w']),height=int(image.attrib['h']),
                    layers=sum(n.tag.split('}')[-1]=='layer' for n in image.iter()))
    if fingerprint(path)!=before: raise ValueError('ORA changed during read')
    return dict(before,**result)


def pinned(expected):
    actual=inspect(expected['path'])
    if any(actual[k]!=expected[k] for k in ('sha256','width','height','layers')): raise ValueError('ORA contract mismatch')
    return actual
