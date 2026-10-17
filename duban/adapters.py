"""可选旧版兼容接口；V1.2默认使用native.py，不需要提供Python模型/邮箱适配模块。"""
import copy, hashlib, importlib
from .store import now

class Adapter:
    def __init__(self,module): self.impl=importlib.import_module(module)
    @property
    def execution_mode(self):
        value=getattr(self.impl,'EXECUTION_MODE','unverified')
        return value if value in ['production','simulation'] else 'unverified'
    def capabilities(self):
        names=['plan_admin','map_columns','plan_feedback','analyze','fetch_mail','authorize','send','lookup_sent']
        return {'module':self.impl.__name__,'execution_mode':self.execution_mode,'functions':{k:callable(getattr(self.impl,k,None)) for k in names},'真实收发验收':'未执行，函数存在不代表通过'}
    def __getattr__(self,key):
        method=getattr(self.impl,key,None)
        if not callable(method): raise RuntimeError('宿主适配模块未提供能力：'+key)
        return method

def _mode(adapter):
    value=adapter.execution_mode if isinstance(adapter,Adapter) else getattr(adapter,'EXECUTION_MODE','unverified')
    return value if value in ['production','simulation'] else 'unverified'

def _success(s,row,answer,adapter):
    row['状态']='已发送'
    row['内容']['发送凭据']={'message_id':str(answer['message_id']),'时间':now(),'execution_mode':_mode(adapter)}
    for t in s.data['active']+s.data['closed']:
        if t['内部任务唯一ID']==row['任务ID']:
            t['最近邮件通知时间']=now(); t['最近通知等级']=row['等级']

def dispatch(store,adapter):
    """发送前提交发送中状态；进程中断后只能先核实。每个队列项单独提交。"""
    result={'发送成功':0,'待授权':0,'结果未知':0,'明确失败':0,'执行模式':_mode(adapter),'成功含义':'仅表示适配器返回已接受，不代表已验证收件箱投递'}
    with store.transaction() as s:
        ids=[r['ID'] for r in s.data['outbox'] if r['状态'] in ['待授权','失败','发送中','结果未知']]
    for oid in ids:
        with store.transaction() as s:
            row=next(r for r in s.data['outbox'] if r['ID']==oid)
            if row['状态'] in ['发送中','结果未知']:
                row['状态']='结果未知'; result['结果未知']+=1; continue
            if str(row['等级']).endswith('报告'):
                from .reports import report_fingerprint, _manifest_valid
                info=s.get_config('reports',{})
                if info.get('fingerprint')!=report_fingerprint(s) or not _manifest_valid(s,info):
                    row['状态']='已失效'; s.pending('待发报告已失效',{'队列ID':row['ID'],'原因':'台账或报告已变化，需要重新生成、入队和授权'})
                    continue
            snapshot=copy.deepcopy(row)
        # 通讯录验证、用户逐封确认或正式平台预授权必须由可信适配器完成。
        try: auth=adapter.authorize(snapshot)
        except Exception: auth={}
        if not isinstance(auth,dict): auth={}
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
        if not isinstance(answer,dict): answer={'status':'unknown'}
        with store.transaction() as s:
            row=next(r for r in s.data['outbox'] if r['ID']==oid)
            if answer.get('status')=='sent' and isinstance(answer.get('message_id'),str) and answer['message_id'].strip():
                _success(s,row,answer,adapter)
                result['发送成功']+=1
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
        if not isinstance(answer,dict): answer={'status':'unknown'}
        with store.transaction() as s:
            current=next(r for r in s.data['outbox'] if r['ID']==row['ID'])
            if current['状态'] not in ['发送中','结果未知']: continue
            if answer.get('status')=='sent' and isinstance(answer.get('message_id'),str) and answer['message_id'].strip():
                _success(s,current,answer,adapter)
            elif answer.get('status')=='not_sent' and answer.get('definitely_not_accepted') is True: current['状态']='失败'
            else: current['状态']='结果未知'
            results.append({'ID':row['ID'],'状态':current['状态']})
    return results
