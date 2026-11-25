"""Small real-desktop action recorder; actions are supplied explicitly by operator."""
import argparse,datetime,json,os,subprocess,time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--log',type=Path,required=True);p.add_argument('operation',choices=['click','keys','text','press','focus','shot','scroll','ctrlclick']);p.add_argument('arguments',nargs='*');a=p.parse_args()
    for line in subprocess.check_output(['systemctl','--user','show-environment'],text=True).splitlines():
        k,_,v=line.partition('=')
        if k in {'DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR'}:os.environ[k]=v
    import pyautogui as g
    g.PAUSE=.25
    before=time.monotonic_ns();args=a.arguments
    if a.operation=='click':g.click(int(args[0]),int(args[1]),clicks=int(args[2]) if len(args)>2 else 1,interval=.12)
    elif a.operation=='ctrlclick':
        with g.hold('ctrl'):g.click(int(args[0]),int(args[1]))
    elif a.operation=='keys':g.hotkey(*args)
    elif a.operation=='press':g.press(args[0],presses=int(args[1]) if len(args)>1 else 1,interval=.1)
    elif a.operation=='text':g.write(args[0],interval=.002)
    elif a.operation=='scroll':g.scroll(int(args[0]))
    elif a.operation=='focus':subprocess.run(['wmctrl','-a',args[0]],check=True)
    elif a.operation=='shot':subprocess.run(['gnome-screenshot','-f',args[0]],check=True)
    a.log.parent.mkdir(parents=True,exist_ok=True)
    with a.log.open('a') as f:f.write(json.dumps(dict(monotonic_ns=before,end_monotonic_ns=time.monotonic_ns(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),operation=a.operation,arguments=args))+'\n')
if __name__=='__main__':main()
