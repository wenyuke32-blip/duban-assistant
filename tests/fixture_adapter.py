"""明确的脚本化模拟宿主，仅用于端到端状态机验收，不能用于生产。"""
import json, os, shutil
from pathlib import Path
EXECUTION_MODE='simulation'

def root(): return Path(os.environ['DUBAN_FIXTURE_DIR'])
def read(name,default):
    p=root()/name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def fetch_mail(cursor):
    messages=read('messages.json',[]); start=int(cursor or 0); stop=min(start+2,len(messages))
    return {'messages':messages[start:stop],'next_cursor':str(stop),'has_more':stop<len(messages)}

def plan_feedback(mail,context): return read('plans.json',{})[mail['id']]
def plan_admin(text,context): return read('admin-plan.json',[])
def map_columns(headers,rows,standard_fields): return read('column-map.json',{})

def analyze(task,history):
    # 固定规则fixture提供结构化结果，绝不是实际大模型语义推理。
    progress=task.get('最新办理进展') or task['任务名称']
    high='资源不足' in progress
    return {'risk':'高' if high else '低','facts':[progress],'hypotheses':['资源依赖可能影响交付，待核实'] if high else ['模拟fixture：无充分信息判断拖延原因'],
      'evidence':[progress],'actions':['模拟建议：核实资源到位日期'] if high else ['模拟建议：核对最新进度'],
      'coordination':['网络部'] if high else [],'category':'资源依赖' if high else '信息不足','next_focus':['模拟跟踪：资源到位日期' if high else '模拟跟踪：下次进度反馈']}

def authorize(row):
    allowed=row['接收人'] in read('allowed-recipients.json',[])
    return {'directory_verified':allowed,'allowed':allowed,'authorization_receipt':'SIMULATION-ONLY-NOT-PLATFORM-AUTH'}

def send(row,authorization):
    receipts=read('receipts.json',{})
    if row['ID'] not in receipts:
        dest=root()/'delivered'/row['ID']; dest.mkdir(parents=True,exist_ok=True)
        names=[]
        for attachment in row['内容']['attachments']:
            src=Path(attachment['path']);shutil.copy2(src,dest/src.name);names.append(src.name)
        receipts[row['ID']]={'recipient':row['接收人'],'attachments':names,'message_id':'SIM-'+row['ID'],'execution_mode':'simulation'}
        (root()/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'status':'sent','message_id':receipts[row['ID']]['message_id']}

def lookup_sent(row):
    receipts=read('receipts.json',{})
    return {'status':'sent','message_id':receipts[row['ID']]['message_id']} if row['ID'] in receipts else {'status':'unknown'}
