"""Loopback-only research viewer, derived from v0.5 workbench. No paid-run route."""
import argparse,json,sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from rr_v05 import load_stimuli
from isolation_protocol import PROTOCOL,PARAMETERS,schedule,messages,select_stimuli,analyze
from journal import status,readonly

ROOT=Path(__file__).resolve().parent
DB=ROOT/'private_exports/rr-isolation-001.sqlite3'
STIM=ROOT/'private_inputs/calm_rr_v42.json'
MIME={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'}

def gate():return json.loads((ROOT/'private_exports/gate_a.json').read_text(encoding='utf-8'))

def payload():
    report=gate();s=status(DB)
    return {'protocol':PROTOCOL,'report':report,'journal':s,'scenarios':[{'id':x['id'],'title':x['title'],'category':x['category']} for x in load_stimuli(STIM)['scenarios']]}

def results():
    d=readonly(DB)
    try:
        rows=[dict(r) for r in d.execute('SELECT e.arm,e.condition_id AS condition,e.repeat_index AS repeat,r.item_id,r.rating FROM ratings r JOIN episodes e ON e.episode_id=r.episode_id')]
        complete=d.execute("SELECT count(*) FROM episodes WHERE status='complete'").fetchone()[0]
        valid=d.execute("SELECT count(*) FROM requests WHERE state='valid'").fetchone()[0]
    finally:d.close()
    if complete!=60 or valid!=120 or len(rows)!=432:
        return {'status':'incomplete','new_ratings':len(rows),'w1':None,'reason':'完整且平衡的 60 对话／120 请求／432 评分尚未形成，暂不计算本次 W1。'}
    human=json.loads((ROOT/'private_exports/human_reference_aggregate.json').read_text(encoding='utf-8'))
    return {'status':'complete','analysis':analyze(rows,human,load_stimuli(STIM))}

class Handler(BaseHTTPRequestHandler):
    def send(self,code,body,kind='application/json; charset=utf-8'):
        if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

    def do_GET(self):
        host=self.headers.get('Host','').split(':')[0].lower()
        if host not in ('127.0.0.1','localhost'):return self.send(403,{'error':'Loopback host required'})
        url=urlparse(self.path);route=url.path
        try:
            if route in ('/','/index.html','/app.js','/style.css'):
                file=ROOT/'web'/('index.html' if route=='/' else route[1:])
                return self.send(200,file.read_bytes(),MIME[file.suffix])
            if route=='/api/health':return self.send(200,{'status':'ready','protocol':PROTOCOL,'workspace':str(ROOT),'live_execution':gate().get('run_status','blocked')})
            if route=='/api/status':return self.send(200,payload())
            if route=='/api/results':return self.send(200,results())
            if route=='/api/export/checkpoint.json':return self.send(200,gate())
            if route=='/api/export/ratings.csv':
                if gate().get('run_status')!='complete_verified':return self.send(409,{'error':'完整结果尚未独立核验'})
                return self.send(200,(ROOT/'private_exports/ratings-real-20261117.csv').read_bytes(),'text/csv; charset=utf-8')
            if route=='/api/preview':
                q=parse_qs(url.query);sid=q.get('scenario',['elevator'])[0];condition=q.get('condition',['none'])[0];arm=q.get('arm',['ISOLATED'])[0]
                stim=load_stimuli(STIM);cell={'arm':arm,'condition':condition,'scenario_id':sid}
                selected=select_stimuli(stim,cell)
                # Preview placeholder is visibly identified and is never a saved model response.
                placeholder=json.dumps({s['id']:'<本对话编码阶段的真实 Yes/No 回答>' for s in selected['scenarios']},ensure_ascii=False)
                return self.send(200,{'parameters':PARAMETERS,'encoding':messages(stim,cell,'encoding'),
                   'rating':messages(stim,cell,'rating',placeholder),'preview_only':True,'scenarios':len(selected['scenarios']),
                   'memory_messages':0 if condition=='none' else 1,'rating_items':sum(len(s['interpretations']) for s in selected['scenarios'])})
            return self.send(404,{'error':'Not found'})
        except (ValueError,KeyError):return self.send(400,{'error':'Invalid selection'})
        except Exception:return self.send(500,{'error':'Local data could not be read'})

    def do_POST(self):self.send(405,{'error':'工作台提供只读查看；真实运行由 Work 协调。'})
    def log_message(self,fmt,*args):pass

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8782);args=p.parse_args()
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
