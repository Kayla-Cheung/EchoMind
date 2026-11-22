import argparse,json,subprocess,sys,time,urllib.request,webbrowser,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def probe(port):
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{port}/api/health',timeout=1) as r:return json.load(r)
    except (OSError,ValueError):return None

def start(port=8782,open_browser=True):
    if not 1024<=port<=65535:raise ValueError('Port must be between 1024 and 65535')
    found=probe(port)
    def matches(h):return h and h.get('protocol')=='RR-ISOLATION-001' and h.get('workspace')==str(ROOT)
    if found and not matches(found):raise RuntimeError('Port belongs to another workspace')
    if not matches(found):
        py=Path(sys.executable);kw={};proc=None
        if os.name=='nt':
            if py.with_name('pythonw.exe').is_file():py=py.with_name('pythonw.exe')
            # Start-Process creates a normal independent Windows background app.
            # No scheduled task, startup registration, account or security changes.
            logs=ROOT/'private_exports';logs.mkdir(exist_ok=True)
            receipt_path=logs/f'service-process-{port}.json'
            # Files avoid inherited pipe handles keeping the launcher blocked
            # after the independent server has already become healthy.
            with (logs/'service-launch.log').open('ab') as startup_log:
                started=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'start_service.ps1'),
                    '-PythonPath',str(py),'-Port',str(port),'-ReceiptPath',str(receipt_path)],cwd=ROOT,
                    stdin=subprocess.DEVNULL,stdout=startup_log,stderr=startup_log,
                    creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
            if started.returncode:raise RuntimeError('Could not start the local workbench; see private_exports/service-launch.log')
            receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig'))
        else:
            kw['start_new_session']=True
            with (ROOT/'private_exports/workbench.log').open('ab') as log:
                proc=subprocess.Popen([str(py),'-B',str(ROOT/'workbench.py'),'--port',str(port)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True,**kw)
        for _ in range(50):
            if matches(probe(port)):break
            if proc is not None and proc.poll() is not None:raise RuntimeError('Workbench failed; see local log')
            time.sleep(.2)
        else:
            if proc is not None:proc.terminate()
            raise RuntimeError('Workbench readiness timeout; see private_exports/service-*.stderr.log')
    url=f'http://127.0.0.1:{port}/'
    if open_browser:webbrowser.open(url)
    return url

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8782);p.add_argument('--no-browser',action='store_true');a=p.parse_args()
    print(start(a.port,not a.no_browser))
