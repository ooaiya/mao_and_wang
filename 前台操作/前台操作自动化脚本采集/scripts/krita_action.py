#!/usr/bin/env python3
"""Invoke exactly one named import action in the specified Krita PID."""
import argparse
import json
import re
from pathlib import Path
import pyatspi
from krita_auto import normalize_button_label

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pid',type=int,required=True);parser.add_argument('--snapshot',action='store_true');parser.add_argument('--discard-document');args=parser.parse_args()
    if args.pid<=1:raise ValueError('exact owned PID required')
    desktop=pyatspi.Registry.getDesktop(0)
    queue=[]
    for i in range(desktop.childCount):
        app=desktop.getChildAtIndex(i)
        try:
            if app is not None and app.get_process_id()==args.pid:queue.append((app,None))
        except Exception:continue
    matches=[];dialogs=[];buttons=[];visited=0;unavailable=0
    labels={'import layer...','导入图层...','匯入圖層...'}
    while queue:
        node,dialog=queue.pop();visited+=1
        if visited>10000:raise RuntimeError('accessibility tree bound exceeded')
        if node is None:unavailable+=1;continue
        try:
            state=node.getState()
            if state.contains(pyatspi.STATE_DEFUNCT):continue
            showing=state.contains(pyatspi.STATE_SHOWING);role=node.getRole();raw_name=node.name or ''
            name=raw_name.replace('&','').replace('…','...').strip().casefold()
            if args.snapshot or args.discard_document:
                if role in (pyatspi.ROLE_FRAME,pyatspi.ROLE_DIALOG,pyatspi.ROLE_FILE_CHOOSER,pyatspi.ROLE_ALERT) and not showing:continue
                if role in (pyatspi.ROLE_DIALOG,pyatspi.ROLE_FILE_CHOOSER,pyatspi.ROLE_ALERT) and showing:
                    dialog=dict(name=raw_name,text=[],buttons=[]);dialogs.append(dialog)
                if dialog is not None:
                    if raw_name:dialog['text'].append(raw_name)
                    if role==pyatspi.ROLE_PUSH_BUTTON and showing:
                        rect=node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
                        dialog['buttons'].append(dict(name=raw_name,box=[rect.x,rect.y,rect.width,rect.height]))
                        buttons.append((node,dialog,raw_name))
            elif role==pyatspi.ROLE_MENU_ITEM and name in labels:matches.append(node)
            queue.extend((node.getChildAtIndex(i),dialog) for i in range(node.childCount))
        except Exception:unavailable+=1
    if args.snapshot:
        print(json.dumps(dict(schema_version=1,ok=True,pid=args.pid,dialogs=dialogs,visited=visited,unavailable_nodes=unavailable,
                              diagnostic='targeted controls only; not a complete Layers tree')));return
    if args.discard_document:
        matches=[]
        labels={"don't save",'dont save','discard','no','不保存','放弃','否','不儲存'}
        for node,dialog,name in buttons:
            text=' '.join(dialog['text'])
            names={args.discard_document,Path(args.discard_document).stem}
            if (normalize_button_label(name) in labels and re.search(r'save|保存|儲存',text,re.I)
                and any(re.search(r'(?<![\w.])'+re.escape(n)+r'(?![\w.])',text,re.I) for n in names)):
                matches.append(node)
        if len(matches)!=1:raise RuntimeError('document-bound discard action is not unique: '+str(len(matches)))
        print(json.dumps(dict(pid=args.pid,action=matches[0].name,document=args.discard_document)),flush=True)
        if not matches[0].queryAction().doAction(0):raise RuntimeError('discard action was rejected')
        return
    if len(matches)!=1:raise RuntimeError('Import Layer action is not unique: '+str(len(matches)))
    action=matches[0].queryAction()
    if action.nActions!=1:raise RuntimeError('Import Layer accessibility action is ambiguous')
    print(json.dumps(dict(pid=args.pid,action=matches[0].name,visited=visited)),flush=True)
    if not action.doAction(0):raise RuntimeError('Import Layer action was rejected')

if __name__=='__main__':main()
