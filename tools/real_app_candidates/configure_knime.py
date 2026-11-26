"""Generate an unexecuted native KNIME weather workflow from bundled examples.

This only writes node settings. Open in the real GUI and use Execute All.
No KNIME executor, data transformation, or memory allocation workload is run.
"""
import argparse,copy,zipfile,subprocess,xml.etree.ElementTree as E
from pathlib import Path
NS='http://www.knime.org/2008/09/XMLConfig'
E.register_namespace('',NS)
def cfg(parent,key):return E.SubElement(parent,'{'+NS+'}config',key=key)
def ent(parent,key,value,kind='xstring'):
    return E.SubElement(parent,'{'+NS+'}entry',key=key,type=kind,value=str(value).lower() if isinstance(value,bool) else str(value))
def child(parent,key):return next(x for x in parent if x.attrib.get('key')==key)
def setv(parent,key,value):
    x=child(parent,key);x.attrib.pop('isnull',None);x.set('value',str(value).lower() if isinstance(value,bool) else str(value))
def arr(parent,key,values,kind='xstring'):
    try:c=child(parent,key);c.clear();c.set('key',key)
    except StopIteration:c=cfg(parent,key)
    ent(c,'array-size',len(values),'xint')
    for i,v in enumerate(values):ent(c,str(i),v,kind)
    return c
def write(path,root):
    path.parent.mkdir(parents=True,exist_ok=True);E.indent(root);E.ElementTree(root).write(path,encoding='UTF-8',xml_declaration=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('--installation',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--workflow',type=Path,required=True);a=p.parse_args()
    if a.workflow.exists():raise ValueError('Refuse to overwrite workflow')
    for target in [a.workflow,a.output]:
        parent=target.resolve().parent
        while not parent.exists():parent=parent.parent
        if subprocess.run(['git','-C',str(parent),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise ValueError('Workflow and real output must be outside Git')
    if not a.input.is_file():raise ValueError('Real prepared input file missing')
    z=zipfile.ZipFile(a.installation/'knime-workspace.zip')
    def template(needle):return E.fromstring(z.read(next(n for n in z.namelist() if n.endswith(needle))))
    csv=template('Building a Simple Classifier/CSV Reader (#14)/settings.xml')
    column=template('Combine Clean and Summarize Spreadsheet Data/Column Filter (#27)/settings.xml')
    num=template('Building a Churn Prediction Model/Number To String (#105)/settings.xml')
    filt=template('CountIf and SumIf/Rule_based Row Filter (#13)/settings.xml')
    math=template('Find Recomme (#111)/Math Formula (#113)/settings.xml')
    rule=template('Apply the mo (#37)/Rule Engine (#34)/settings.xml')
    sort=template('CountIf and SumIf/Sorter (#29)/settings.xml')
    workflow=template('Building a Simple Classifier/workflow.knime')
    # Explicit source types. Header preparation only adds field names; all original
    # observations, values, flags and ordering remain unmodified.
    model=child(csv,'model');settings=child(model,'settings');selection=child(settings,'file_selection')
    fs=child(selection,'file_system_chooser__Internals');setv(fs,'convenience_fs_category','LOCAL')
    path=child(selection,'path');setv(path,'file_system_type','LOCAL');setv(path,'file_system_specifier','');child(path,'file_system_specifier').set('isnull','true');setv(path,'path',a.input.resolve())
    spec=child(model,'table_spec_config_Internals');individual=child(spec,'individual_specs');first=child(individual,next(iter(individual)).attrib['key']);first.set('key',str(a.input.resolve()))
    original_columns=list(first)[1:];integer=copy.deepcopy(original_columns[0]);string=copy.deepcopy(original_columns[1])
    first.clear();first.set('key',str(a.input.resolve()));ent(first,'num_columns',8,'xint')
    transform=child(spec,'table_transformation');columns=child(transform,'columns');old=list(columns);integer_t=copy.deepcopy(old[0]);string_t=copy.deepcopy(old[1]);columns.clear();columns.set('key','columns');ent(columns,'num_columns',8,'xint')
    names=['ID','DATE','ELEMENT','DATA_VALUE','M_FLAG','Q_FLAG','S_FLAG','OBS_TIME']
    for i,name in enumerate(names):
        numeric=name in {'DATE','DATA_VALUE'};c=copy.deepcopy(integer if numeric else string);c.set('key',str(i));setv(c,'name',name);first.append(c)
        c=copy.deepcopy(integer_t if numeric else string_t);c.set('key',str(i));setv(c,'name',name);setv(child(c,'external_spec'),'name',name);setv(c,'position',i);columns.append(c)
    arr(columns,'intersection_indices',list(range(8)),'xint')
    setv(child(transform,'unknown_columns_transformation'),'position',8);setv(spec,'source_group_id',a.input.resolve())
    setv(child(csv,'internal_node_subsettings'),'memory_policy','CacheSmallInMemory')
    keep=['ID','DATE','ELEMENT','DATA_VALUE','Q_FLAG'];m=child(child(column,'model'),'column-filter');arr(m,'included_names',keep);arr(m,'excluded_names',['M_FLAG','S_FLAG','OBS_TIME']);setv(m,'enforce_option','EnforceInclusion')
    m=child(child(num,'model'),'include');arr(m,'included_names',['DATE']);arr(m,'excluded_names',['DATA_VALUE']);setv(m,'enforce_option','EnforceInclusion')
    date=copy.deepcopy(rule);setv(date,'factory','org.knime.time.node.convert.stringtodatetime.StringToDateTimeNodeFactory');setv(date,'node-name','String to Date&Time');m=child(date,'model');m.clear();m.set('key','model')
    c=copy.deepcopy(child(child(num,'model'),'include'));c.set('key','col_select');m.append(c)
    for key,value,kind in [('replace_or_append','Replace selected columns','xstring'),('suffix','(Date&Time)','xstring'),('date_format','yyyyMMdd','xstring'),('locale','en-US','xstring'),('cancel_on_fail',True,'xboolean'),('typeEnum','LOCAL_DATE','xstring')]:ent(m,key,value,kind)
    m=child(filt,'model');arr(m,'rules',['MISSING $Q_FLAG$ AND $ELEMENT$ IN ("TMAX", "TMIN", "TAVG", "PRCP") => TRUE','TRUE => FALSE'])
    m=child(math,'model');setv(m,'expression','$DATA_VALUE$ / 10.0');setv(m,'replaced_column','CONVERTED_VALUE');setv(m,'append_column',False)
    m=child(rule,'model');arr(m,'rules',['$ELEMENT$ = "PRCP" => "mm"','TRUE => "degC"']);setv(m,'new-column-name','UNIT')
    m=child(sort,'model');arr(m,'incllist',['ID','DATE','ELEMENT']);arr(m,'sortOrder',[True]*3,'xboolean');arr(m,'alphaNumStringComp',[False]*3,'xboolean')
    # Legacy native CSV Writer is used when the portable distribution has no
    # Parquet extension. Native GUI validation remains required before execution.
    writer=copy.deepcopy(rule);setv(writer,'factory','org.knime.base.node.io.csvwriter.CSVWriterNodeFactory');setv(writer,'node-name','CSV Writer');m=child(writer,'model');m.clear();m.set('key','model')
    for k,v,t in [('filename',str(a.output.resolve()),'xstring'),('colSeparator',',','xstring'),('quoteBegin','"','xstring'),('quoteEnd','"','xstring'),('quoteReplacement','""','xstring'),('quoteMode','STRINGS','xstring'),('sepReplacePattern','_','xstring'),('ReplSepInStrings',False,'xboolean'),('writeColHeader',True,'xboolean'),('writeRowHeader',False,'xboolean'),('missing','','xstring'),('decimalSeparator','.','xchar'),('lineEndingMode','SYST','xstring'),('charSet','UTF-8','xstring'),('scientificExtrema',True,'xboolean'),('commentBegin','#','xstring'),('commentEnd','','xstring'),('commentIndent','#','xstring'),('addTime',False,'xboolean'),('addUser',False,'xboolean'),('addTablename',False,'xboolean'),('userCommentLine','','xstring'),('skipWriteColHeaderOnAppend',True,'xboolean'),('isAppendToFile',False,'xboolean'),('gzip',False,'xboolean'),('fileOverwritePolicy','Abort','xstring')]:ent(m,k,v,t)
    for key in ['annotations','nodes','connections']:
        c=child(workflow,key);c.clear();c.set('key',key)
    setv(workflow,'customDescription','NOAA GHCN-Daily 2024 quality-filtered temperature/precipitation conversion; GUI Execute All only; no streaming or forced GC/reset.')
    backend=cfg(workflow,'tableBackend');ent(backend,'class','org.knime.core.data.columnar.ColumnarTableBackend')
    nodes=[('CSV Reader',csv),('Column Filter',column),('Number To String',num),('String to DateTime',date),('Quality and Element Filter',filt),('Math Formula',math),('Unit Rule Engine',rule),('Sorter',sort),('CSV Writer',writer)]
    for i,(name,node) in enumerate(nodes,1):
        setv(node,'state','CONFIGURED');setv(node,'hasContent',False)
        annotation=child(node,'nodeAnnotation')
        for e in annotation:
            if e.attrib.get('key')=='text':e.set('value','')
            if e.attrib.get('key')=='styles':e.clear();e.set('key','styles')
        for key in ['ports']:
            c=child(node,key);c.clear();c.set('key',key)
        # Rebuild output-port metadata without data. The writer is a sink.
        if i<9:
            c=cfg(child(node,'ports'),'port_1');ent(c,'index',1,'xint');e=ent(c,'port_dir_location','');e.set('isnull','true')
        location=f'{name} (#{i})/settings.xml';write(a.workflow/location,node)
        c=cfg(child(workflow,'nodes'),f'node_{i}')
        for k,v,t in [('id',i,'xint'),('node_settings_file',location,'xstring'),('node_is_meta',False,'xboolean'),('node_type','NativeNode','xstring'),('ui_classname','org.knime.core.node.workflow.NodeUIInformation','xstring')]:ent(c,k,v,t)
        arr(cfg(c,'ui_settings'),'extrainfo.node.bounds',[100+(i-1)%5*170,150+(i-1)//5*210,100,90],'xint')
        if i>1:
            c=cfg(child(workflow,'connections'),f'connection_{i-2}')
            for k,v in [('sourceID',i-1),('destID',i),('sourcePort',1),('destPort',1)]:ent(c,k,v,'xint')
    write(a.workflow/'workflow.knime',workflow)
    print(a.workflow)
if __name__=='__main__':main()
