"""部署方提供可信的宿主适配模块。本文件不假造cmcc-mail工具或认证参数。"""
import copy, hashlib, importlib
from .store import now

class Adapter:
    def __init__(self,module): self.impl=importlib.import_module(module)
    def __getattr__(self,key):
        method=getattr(self.impl,key,None)
        if not callable(method): raise RuntimeError('宿主适配模块未提供能力：'+key)
        return method

def dispatch(store,adapter):
    """发送前提交发送中状态；进程中断后只能先核实。每个队列项单独提交。"""
    result={'发送成功':0,'待授权':0,'结果未知':0,'明确失败':0}
    with store.transaction() as s:
        ids=[r['ID'] for r in s.data['outbox'] if r['状态'] in ['待授权','失败','发送中','结果未知']]
    for oid in ids:
        with store.transaction() as s:
            row=next(r for r in s.data['outbox'] if r['ID']==oid)
            if row['状态'] in ['发送中','结果未知']:
                row['状态']='结果未知'; result['结果未知']+=1; continue
            snapshot=copy.deepcopy(row)
        # 通讯录验证、用户逐封确认或正式平台预授权必须由可信适配器完成。
        try: auth=adapter.authorize(snapshot)
        except Exception: auth={}
        if auth.get('directory_verified') is not True or auth.get('allowed') is not True or not auth.get('authorization_receipt'):
            result['待授权']+=1; continue
        with store.transaction() as s:
            row=next(r for r in s.data['outbox'] if r['ID']==oid)
            if row['状态'] not in ['待授权','失败']: continue
            if row!=snapshot: continue  # 授权期间业务变化，重新授权
            # 附件变更使授权对象失效，禁止发送新报告到旧队列。
            from pathlib import Path
            invalid=any(not Path(a['path']).is_file() or hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()!=a['sha256'] for a in row['内容']['attachments'])
            if invalid:
                row['状态']='已失效'; continue
            row['状态']='发送中'; row['尝试次数']=int(row['尝试次数'] or 0)+1
        try:
            answer=adapter.send(snapshot,auth)  # 适配器应使用队列ID作合法幂等关联键
        except Exception:
            answer={'status':'unknown'}  # 不记录原始异常，避免认证数据泄漏
        with store.transaction() as s:
            row=next(r for r in s.data['outbox'] if r['ID']==oid)
            if answer.get('status')=='sent' and answer.get('message_id'):
                row['状态']='已发送'; row['内容']['发送凭据']={'message_id':str(answer['message_id']),'时间':now()}
                result['发送成功']+=1
                for t in s.data['active']+s.data['closed']:
                    if t['内部任务唯一ID']==row['任务ID']:
                        t['最近邮件通知时间']=now(); t['最近通知等级']=row['等级']
            elif answer.get('status')=='not_sent' and answer.get('definitely_not_accepted') is True:
                row['状态']='失败'; result['明确失败']+=1
            else:
                row['状态']='结果未知'; result['结果未知']+=1
    return result

def reconcile(store,adapter):
    results=[]
    with store.transaction() as s:
        rows=copy.deepcopy([r for r in s.data['outbox'] if r['状态'] in ['发送中','结果未知']])
    for row in rows:
        try: answer=adapter.lookup_sent(row)
        except Exception: answer={'status':'unknown'}
        with store.transaction() as s:
            current=next(r for r in s.data['outbox'] if r['ID']==row['ID'])
            if answer.get('status')=='sent' and answer.get('message_id'):
                current['状态']='已发送'; current['内容']['发送凭据']={'message_id':str(answer['message_id']),'时间':now()}
            elif answer.get('status')=='not_sent' and answer.get('definitely_not_accepted') is True: current['状态']='失败'
            else: current['状态']='结果未知'
            results.append({'ID':row['ID'],'状态':current['状态']})
    return results
