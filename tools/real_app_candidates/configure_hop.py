"""Generate a native, unexecuted NOAA Hop pipeline from official bundled samples."""
import argparse,copy,json,subprocess,xml.etree.ElementTree as E
from pathlib import Path

def setv(parent,key,value):
    node=parent.find(key)
    if node is None:node=E.SubElement(parent,key)
    node.text=str(value)
    return node

def child(parent,key):
    node=parent.find(key)
    if node is None:node=E.SubElement(parent,key)
    return node

def main():
    p=argparse.ArgumentParser();p.add_argument('--installation',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--sort-rows',type=int,default=1000000);a=p.parse_args()
    if not a.input.is_file():raise ValueError('Real prepared input missing')
    if a.project.exists() or a.config.exists() or a.output.exists():raise ValueError('Refuse to overwrite a project, config or output')
    if a.sort_rows<=0:raise ValueError('Sort row buffer must be positive')
    for target in [a.project,a.config,a.output]:
        parent=target.resolve().parent
        while not parent.exists():parent=parent.parent
        if subprocess.run(['git','-C',str(parent),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise ValueError('Real projects/config/output must be outside Git')
    templates={};base=None
    for path in (a.installation/'config/projects/samples').rglob('*.hpl'):
        root=E.parse(path).getroot()
        if base is None:base=copy.deepcopy(root)
        for t in root.findall('transform'):
            kind=t.findtext('type')
            if kind not in templates:templates[kind]=copy.deepcopy(t)
    names=['CSV observations','Select and type columns','Quality and element filter','Convert documented units','Assign output units','Station date sort','Weather CSV output']
    kinds=['CSVInput','SelectValues','FilterRows','Calculator','Formula','SortRows','TextFileOutput']
    nodes=[copy.deepcopy(templates[k]) for k in kinds]
    for i,(name,t) in enumerate(zip(names,nodes)):
        setv(t,'name',name);setv(t,'copies',1);setv(t,'distribute','Y');setv(child(t,'GUI'),'xloc',100+i%4*220);setv(child(t,'GUI'),'yloc',130+i//4*240)
    reader,select,filter_,calc,formula,sort,writer=nodes
    setv(reader,'filename',a.input.resolve());setv(reader,'rownum_field','');setv(reader,'lazy_conversion','N');setv(reader,'parallel','N');setv(reader,'header','Y');setv(reader,'separator',',');setv(reader,'encoding','UTF-8');fields=child(reader,'fields');fields.clear()
    for name in ['ID','DATE','ELEMENT','DATA_VALUE','M_FLAG','Q_FLAG','S_FLAG','OBS_TIME']:
        f=E.SubElement(fields,'field')
        for k,v in [('name',name),('type','String'),('length',-1),('precision',-1),('trim_type','none')]:setv(f,k,v)
    fields=child(select,'fields');fields.clear()
    for name in ['ID','DATE','ELEMENT','DATA_VALUE','Q_FLAG']:
        f=E.SubElement(fields,'field');setv(f,'name',name)
    setv(fields,'select_unspecified','N')
    for name,kind,mask in [('DATE','Date','yyyyMMdd'),('DATA_VALUE','Integer','')]:
        meta=E.SubElement(fields,'meta')
        for k,v in [('name',name),('rename',name),('type',kind),('length',-1),('precision',-1),('conversion_mask',mask),('date_format_lenient','false'),('lenient_string_to_number','false')]:setv(meta,k,v)
    compare=child(filter_,'compare');compare.clear();root=E.SubElement(compare,'condition');setv(root,'negated','N');conditions=E.SubElement(root,'conditions')
    quality=E.SubElement(conditions,'condition');setv(quality,'negated','N');setv(quality,'leftvalue','Q_FLAG');setv(quality,'function','IS NULL')
    group=E.SubElement(conditions,'condition');setv(group,'negated','N');setv(group,'operator','AND');ors=E.SubElement(group,'conditions')
    for i,element in enumerate(['TMAX','TMIN','TAVG','PRCP']):
        c=E.SubElement(ors,'condition');setv(c,'negated','N')
        if i:setv(c,'operator','OR')
        setv(c,'leftvalue','ELEMENT');setv(c,'function','=');v=E.SubElement(c,'value')
        for k,value in [('name','constant'),('type','String'),('text',element),('length',-1),('precision',-1),('isnull','N')]:setv(v,k,value)
    setv(filter_,'send_true_to',names[3]);setv(filter_,'send_false_to','Rejected observations')
    for old in list(calc.findall('calculation')):calc.remove(old)
    # Calculator chooses arithmetic from the LEFT operand's runtime type, not
    # the declared result type. Integer DATA_VALUE / Number TEN truncates.
    # Put a native Number scale on the left; preserve DATA_VALUE as Integer.
    for name,op,left,right,remove in [('UNIT_SCALE','CONSTANT','0.1','','Y'),('CONVERTED_VALUE','MULTIPLY','UNIT_SCALE','DATA_VALUE','N')]:
        c=E.SubElement(calc,'calculation')
        for k,v in [('field_name',name),('calc_type',op),('field_a',left),('field_b',right),('remove',remove),('value_type','Number'),('value_length',-1),('value_precision',-1)]:setv(c,k,v)
    fs=child(formula,'formulas');fs.clear();f=E.SubElement(fs,'formula')
    for k,v in [('field_name','UNIT'),('formula','IF([ELEMENT]="PRCP","mm","degC")'),('value_type',2),('value_length',-1),('value_precision',-1),('replace_field','')]:setv(f,k,v)
    temp=a.project.resolve()/'sort_tmp';temp.mkdir(parents=True);setv(sort,'directory',temp);setv(sort,'prefix','ghcn_sort');setv(sort,'sort_size',a.sort_rows);setv(sort,'free_memory','');setv(sort,'unique_rows','N');setv(sort,'compress','N');fields=child(sort,'fields');fields.clear()
    for name in ['ID','DATE','ELEMENT']:
        f=E.SubElement(fields,'field')
        for k,v in [('name',name),('ascending','Y'),('case_sensitive','Y'),('collator_enabled','N'),('presorted','N')]:setv(f,k,v)
    setv(writer,'separator',',');setv(writer,'enclosure','"');setv(writer,'header','Y');setv(writer,'footer','N');setv(writer,'format','UNIX');setv(writer,'encoding','UTF-8');setv(writer,'compression','None');file=child(writer,'file');setv(file,'name',a.output.resolve().with_suffix(''));setv(file,'extention','csv');setv(file,'append','N');setv(file,'split','N');setv(file,'haspartno','N');setv(file,'add_date','N');setv(file,'add_time','N');fields=child(writer,'fields');fields.clear()
    for name,kind,mask in [('ID','String',''),('DATE','Date','yyyy-MM-dd'),('ELEMENT','String',''),('DATA_VALUE','Integer','0'),('Q_FLAG','String',''),('CONVERTED_VALUE','Number','0.0########'),('UNIT','String','')]:
        f=E.SubElement(fields,'field')
        for k,v in [('name',name),('type',kind),('format',mask),('length',-1),('precision',-1),('nullif','')]:setv(f,k,v)
    rejected=copy.deepcopy(templates['Dummy']);setv(rejected,'name','Rejected observations');setv(child(rejected,'GUI'),'xloc',550);setv(child(rejected,'GUI'),'yloc',560)
    for t in list(base):
        if t.tag not in {'info','notepads','order'}:base.remove(t)
    setv(child(base,'info'),'name','NOAA_Q1_weather_conversion');setv(child(base,'info'),'description','Real quality-filtered GHCN-Daily unit conversion, station/date sort and output. GUI Run only.');child(base,'notepads').clear();order=child(base,'order');order.clear()
    for left,right in [*list(zip(names,names[1:])),(names[2],'Rejected observations')]:
        h=E.SubElement(order,'hop');setv(h,'from',left);setv(h,'to',right);setv(h,'enabled','Y')
    for t in [*nodes,rejected]:base.append(t)
    E.indent(base);E.ElementTree(base).write(a.project/'NOAA_Q1_weather_conversion.hpl',encoding='UTF-8',xml_declaration=True)
    metadata=a.project/'metadata/pipeline-run-configuration';metadata.mkdir(parents=True)
    source=a.installation/'config/projects/samples/metadata/pipeline-run-configuration/local.json';(metadata/'local.json').write_text(source.read_text())
    (a.project/'project-config.json').write_text(json.dumps({'metadataBaseFolder':'${PROJECT_HOME}/metadata','unitTestsBasePath':'${PROJECT_HOME}','dataSetsCsvFolder':'${PROJECT_HOME}/datasets','enforcingExecutionInHome':True,'config':{'variables':[]}},indent=2))
    a.config.mkdir(parents=True);(a.config/'hop-config.json').write_text(json.dumps({'projectsConfig':{'enabled':True,'projectMandatory':True,'defaultProject':'weather','standardParentProject':'weather','projectConfigurations':[{'projectName':'weather','projectHome':str(a.project.resolve()),'configFilename':'project-config.json'}]}},indent=2));print(a.project/'NOAA_Q1_weather_conversion.hpl')
if __name__=='__main__':main()
