"""Configure a GUI-saved Kdenlive 21.12 two-video/two-audio project; no rendering."""
import argparse,copy,xml.etree.ElementTree as E
from pathlib import Path

def prop(node,name,value):
    item=node.find("property[@name='%s']"%name)
    if item is None:item=E.SubElement(node,'property',name=name)
    item.text=str(value)

def main():
    p=argparse.ArgumentParser();p.add_argument('--template',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=120);a=p.parse_args()
    import subprocess
    if subprocess.run(['git','-C',str(a.output.resolve().parent),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise SystemExit('Project output must be outside Git')
    tree=E.parse(a.template);root=tree.getroot();fps=int(root.find('profile').get('frame_rate_num'));assert fps==30
    def tc(frame):return f'{frame//(fps*3600):02d}:{frame//(fps*60)%60:02d}:{frame//fps%60:02d}.{round(frame%fps*1000/fps):03d}'
    end=tc(a.seconds*fps-1)
    # GUI template has two real media bin sources and BBB on V1/A1/A2.
    for pl in root.findall('playlist'):
        if pl.get('id')=='main_bin':continue
        for en in pl.findall('entry'):en.set('in',tc(60*fps));en.set('out',tc((60+a.seconds)*fps-1))
    for tr in root.findall('tractor'):tr.set('out',end)
    root.find("producer[@id='black_track']").set('out',end)
    upper=copy.deepcopy(root.find("producer[@id='producer1']"));assert upper is not None
    upper.set('id','real_pip_video');prop(upper,'set.test_audio',1);prop(upper,'set.test_image',0)
    filt=E.SubElement(upper,'filter',{'in':tc(0),'out':upper.get('out')})
    for k,v in {'mlt_service':'affine','kdenlive:id':'affine','transition.rect':'960 540 960 540 1','transition.distort':0,'transition.valign':'middle','transition.halign':'center','transition.fill':1}.items():prop(filt,k,v)
    playlist=root.find("playlist[@id='playlist6']");root.insert(list(root).index(playlist),upper)
    en=E.SubElement(playlist,'entry',producer='real_pip_video',attrib={'in':tc(100*fps),'out':tc((100+a.seconds)*fps-1)})
    source_id=upper.find("property[@name='kdenlive:id']").text;prop(en,'kdenlive:id',source_id)
    main=root.find("playlist[@id='main_bin']")
    for k,v in {'kdenlive:docproperties.zonein':0,'kdenlive:docproperties.zoneout':a.seconds*fps,'kdenlive:docproperties.groups':'[]','kdenlive:docproperties.position':0}.items():prop(main,k,v)
    prop(root.find("tractor[@id='tractor2']"),'kdenlive:track_name','BBB base 60s excerpt')
    prop(root.find("tractor[@id='tractor3']"),'kdenlive:track_name','ToS inset 100s excerpt')
    E.indent(tree,space=' ');tree.write(a.output,encoding='utf-8',xml_declaration=True)
if __name__=='__main__':main()
