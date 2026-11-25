"""Blender --python configuration and result observer; GUI F12 starts computation."""
import datetime,json,os,time
from pathlib import Path
import bpy

config=json.loads(Path(os.environ['TEAMOOM_BLENDER_CONFIG']).read_text())
folder=Path(config['capture_directory']);output=Path(config['output'])
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.progressive='PATH';scene.cycles.samples=int(config['samples'])
scene.render.resolution_x=int(config['width']);scene.render.resolution_y=int(config['height']);scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(output);scene.render.use_file_extension=True

def emit(kind,detail):
    with (folder/'phase_trace.jsonl').open('a') as f:f.write(json.dumps({'kind':kind,'detail':detail,'monotonic_ns':time.monotonic_ns(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})+'\n')

info={'source':bpy.data.filepath,'version':bpy.app.version_string,'scene':scene.name,'device':scene.cycles.device,'sampling':scene.cycles.progressive,'samples':scene.cycles.samples,'resolution':[scene.render.resolution_x,scene.render.resolution_y],'frame':scene.frame_current,'output':str(output),'submission':'GUI F12 only'}
Path(config['parameters_output']).write_text(json.dumps(info,indent=2))
def complete(s):
    bpy.data.images['Render Result'].save_render(s.render.filepath,scene=s)
    emit('task_complete','Native render_complete callback after real PNG saved')
bpy.app.handlers.render_complete.append(complete)
emit('app_ready',info)
