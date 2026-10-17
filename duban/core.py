from __future__ import annotations
import copy, hashlib, json, re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from .store import FIELDS, DEPTS, TZ, now, uid, stamp

STATES=['未开始','办理中','受阻','待验收','已完成','已取消']
RISKS=['未研判','低','中','高','紧急']
CLOSED=['已完成','已取消']
DATES=['下达日期','原定截止日期','预计完成日期','实际完成日期']
AI_FIELDS=['当前AI风险等级','可能拖延原因','AI分析依据','AI整改建议','需要协调事项','最新AI研判时间']
PROTECTED=['内部任务唯一ID','创建时间','重新开启次数','累计延期次数','更新时间','最近更新时间']+AI_FIELDS+['最近邮件通知时间','最近通知等级','最近反馈来源','数据来源']
EMAIL=re.compile(r'^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$')

def day(value):
    if isinstance(value,datetime): return value.date().isoformat()
    if isinstance(value,date): return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()

def validate(fields,create=False):
    bad=set(fields)-set(FIELDS)
    if bad: raise ValueError('未知任务字段：'+','.join(bad))
    out=dict(fields)
    if create:
        for key in ['任务名称','主责部门','原定截止日期']:
            if not out.get(key): raise ValueError('缺少关键字段：'+key)
    if '主责部门' in out and out['主责部门'] not in DEPTS: raise ValueError('主责部门不在四部门范围')
    if '办理状态' in out and out['办理状态'] not in STATES: raise ValueError('办理状态无效')
    if '协办部门' in out:
        vals=out['协办部门']
        if isinstance(vals,str): vals=[v.strip() for v in re.split('[,，、;；]',vals) if v.strip()]
        if not isinstance(vals,list) or any(v not in DEPTS for v in vals): raise ValueError('协办部门无效')
        out['协办部门']='、'.join(dict.fromkeys(vals))
    for k in DATES:
        if k in out and out[k] not in ('',None): out[k]=day(out[k])
    if '完成百分比' in out and out['完成百分比'] not in ('',None):
        p=out['完成百分比']
        if isinstance(p,bool) or not isinstance(p,(float,int)) or not 0<=p<=100: raise ValueError('完成百分比须为0至100的明确数字')
    if out.get('联系邮箱') and not EMAIL.fullmatch(out['联系邮箱']): raise ValueError('邮箱格式无效')
    return out

def all_tasks(s): return s.data['active']+s.data['closed']
def find(s,tid):
    rows=[t for t in all_tasks(s) if t['内部任务唯一ID']==tid]
    if len(rows)!=1: raise ValueError('任务ID不存在或不唯一')
    return rows[0]

def create(s,fields,source='管理员',at=None):
    if set(fields)&set(PROTECTED): raise ValueError('不能写入系统保护字段')
    fields=validate(fields,True)
    if any(t['任务名称']==fields['任务名称'] and t['主责部门']==fields['主责部门'] for t in all_tasks(s)):
        raise ValueError('同名同部门任务已存在，请明确更新任务或提交待确认')
    clock=at or now(); stamp(clock)
    t={k:'' for k in FIELDS}; t.update({'内部任务唯一ID':uid(),'办理状态':'未开始','当前AI风险等级':'未研判','重新开启次数':0,'累计延期次数':0})
    t.update(fields); t.update({'创建时间':now(),'更新时间':now(),'最近更新时间':clock,'数据来源':source,'最近反馈来源':source})
    if t['办理状态']=='已完成' and not t['实际完成日期']: t['实际完成日期']=stamp(clock).date().isoformat()
    s.data['closed' if t['办理状态'] in CLOSED else 'active'].append(t)
    s.history(t['内部任务唯一ID'],'新增',{'字段':fields,'来源':source})
    return t

def update(s,tid,fields,source='管理员',at=None,admin=True):
    if set(fields)&set(PROTECTED): raise ValueError('不能修改系统保护字段')
    if not admin:
        allowed={'办理状态','完成百分比','最新办理进展','存在问题','延期原因','预计完成日期','实际完成日期'}
        if set(fields)-allowed: raise ValueError('主管反馈不能修改任务定义、联系人或原截止日期')
    fields=validate(fields); t=find(s,tid); before=copy.deepcopy(t); clock=at or now()
    if stamp(clock)<stamp(t['最近更新时间']): return '旧反馈已跳过'
    if not fields: return '无变更'
    expected=fields.get('预计完成日期')
    if expected and expected!=t.get('预计完成日期') and expected>t['原定截止日期']:
        t['累计延期次数']=int(t.get('累计延期次数') or 0)+1
    was_closed=t['办理状态'] in CLOSED
    t.update(fields)
    if t['办理状态']=='已完成' and not t['实际完成日期']: t['实际完成日期']=stamp(clock).date().isoformat()
    is_closed=t['办理状态'] in CLOSED
    if was_closed and not is_closed:
        t['重新开启次数']=int(t['重新开启次数'] or 0)+1; t['实际完成日期']=''
    for key in ['active','closed']:
        s.data[key]=[x for x in s.data[key] if x['内部任务唯一ID']!=tid]
    s.data['closed' if is_closed else 'active'].append(t)
    t.update({'更新时间':now(),'最近更新时间':clock,'最近反馈来源':source})
    kind='重新开启' if was_closed and not is_closed else ('办结' if not was_closed and is_closed else '更新')
    # 业务更新使尚未发送的旧通知失效；未知结果的通知保留供核实。
    for row in s.data['outbox']:
        if row['任务ID']==tid and row['状态'] in ['待授权','失败']: row['状态']='已失效'
    s.history(tid,kind,{'原值':{k:before[k] for k in fields},'新值':fields,'来源':source})
    return kind

def delete(s,tid,admin=True):
    if not admin: raise ValueError('邮件不得删除任务')
    t=find(s,tid)
    for k in ['active','closed']: s.data[k]=[x for x in s.data[k] if x['内部任务唯一ID']!=tid]
    for row in s.data['outbox']:
        if row['任务ID']==tid and row['状态'] in ['待授权','失败']: row['状态']='已失效'
    s.history(tid,'管理员删除',{'任务名称':t['任务名称']})
    return '已删除'

def contacts(s,fields):
    if set(fields)-{'部门名称','主管姓名','主管邮箱','管理员姓名','管理员邮箱'}: raise ValueError('未知联系人字段')
    if fields.get('部门名称') not in DEPTS: raise ValueError('部门无效')
    for k in ['主管邮箱','管理员邮箱']:
        if fields.get(k) and not EMAIL.fullmatch(fields[k]): raise ValueError('邮箱格式错误')
    row=next(r for r in s.data['contacts'] if r['部门名称']==fields['部门名称'])
    if any(row.get(k,'')!=v for k,v in fields.items()):
        for queued in s.data['outbox']:
            if queued['状态'] in ['待授权','失败']: queued['状态']='已失效'
    row.update(fields)
    return row

def stats(tasks,today=None):
    today=today or datetime.now(TZ).date(); ds=today.isoformat()
    done=[t for t in tasks if t['办理状态']=='已完成']; live=[t for t in tasks if t['办理状态'] not in CLOSED]
    eligible=[t for t in tasks if t['办理状态']!='已取消']
    ontime=[t for t in done if t.get('实际完成日期') and t['实际完成日期']<=t['原定截止日期']]
    return {'任务总数':len(tasks),'有效任务数':len(eligible),'已完成数':len(done),'未完成数':len(live),
      '已取消数':sum(t['办理状态']=='已取消' for t in tasks),
      '完成率':round(len(done)/len(eligible),4) if eligible else None,
      '按期完成率':round(len(ontime)/len(done),4) if done else None,
      '逾期数量':sum(t['原定截止日期']<ds for t in live),
      '临期任务':sum(0<=(date.fromisoformat(t['原定截止日期'])-today).days<=7 for t in live),
      '高风险任务':sum(t['当前AI风险等级'] in ['高','紧急'] for t in live),
      '受阻任务':sum(t['办理状态']=='受阻' for t in live)}

def grouped(tasks,key):
    return {v:stats([t for t in tasks if t.get(key)==v]) for v in sorted(set(t.get(key,'') for t in tasks))}

def apply_analysis(s,tid,result):
    t=find(s,tid)
    required={'risk','facts','hypotheses','evidence','actions','coordination','category','next_focus'}
    if set(result)!=required or result['risk'] not in RISKS[1:]: raise ValueError('AI研判结构无效')
    if not isinstance(result['category'],str) or not result['category'].strip(): raise ValueError('原因分类应为非空文本')
    for key in required-{'risk','category'}:
        if not isinstance(result[key],list) or not all(isinstance(x,str) for x in result[key]): raise ValueError('AI研判列表无效')
    if not result['evidence']: raise ValueError('AI研判必须提供依据')
    # 引证必须包含可查当前字段或72小时历史原文；不是模型自报置信度。
    corpus='\n'.join(str(v) for k,v in t.items() if k not in AI_FIELDS)+'\n'+json.dumps([r['内容'] for r in s.data['history'] if r['任务ID']==tid and r['类型']!='AI研判'],ensure_ascii=False)
    if any(e not in corpus for e in result['evidence']): raise ValueError('AI引用了不可核对的依据')
    old=t['当前AI风险等级']
    t.update({'当前AI风险等级':result['risk'],'可能拖延原因':'；'.join(result['hypotheses']),
              'AI分析依据':'；'.join(result['evidence']),'AI整改建议':'；'.join(result['actions']),
              '需要协调事项':'；'.join(result['coordination']),'最新AI研判时间':now()})
    s.set_config('analysis:'+tid,result)
    s.history(tid,'AI研判',result)
    return old!=result['risk']

def scan(s,adapter=None,force=False):
    result={'已研判':0,'需宿主AI研判':[],'失败':[]}
    for t in s.data['active']:
        last=t.get('最新AI研判时间'); days=(date.fromisoformat(t['原定截止日期'])-datetime.now(TZ).date()).days
        due=force or not last or stamp(t['最近更新时间'])>stamp(last) or days<=7 or (datetime.now(TZ)-stamp(last)).days>=7
        if not due: continue
        tid=t['内部任务唯一ID']
        if not adapter:
            result['需宿主AI研判'].append(tid); continue
        try:
            history=[r for r in s.data['history'] if r['任务ID']==tid]
            apply_analysis(s,tid,adapter.analyze(copy.deepcopy(t),copy.deepcopy(history)))
            result['已研判']+=1
        except Exception as e:
            s.pending('AI研判失败',{'任务ID':tid,'错误类型':type(e).__name__}); result['失败'].append(tid)
    return result

def match_feedback(s,item,sender,at):
    # 邮件信封身份来自邮箱适配器，不接受正文指定的sender/admin。
    owners=[r['部门名称'] for r in s.data['contacts'] if r.get('主管邮箱','').casefold()==sender.casefold()]
    if len(owners)!=1: raise ValueError('发件人未唯一对应部门主管')
    dept=owners[0]; evidence=item.get('evidence',[])
    if item.get('action')=='create':
        raise ValueError('新增事项须使用正式下达校验路径')
    if item.get('action')!='update': raise ValueError('邮件仅允许进度更新')
    t=find(s,item.get('task_id',''))
    if t['主责部门']!=dept: raise ValueError('发件人部门与主责部门不一致')
    candidates=item.get('candidate_ids',[])
    if candidates!=[t['内部任务唯一ID']]: raise ValueError('候选任务不唯一')
    if not isinstance(evidence,list) or len(evidence)<1: raise ValueError('缺少可核对原文证据')
    return t

def process_mail(s,mail,plan):
    mid=mail['id']; sender=mail['sender']; stamp(mail['sent_at'])
    if not mail.get('body') or not isinstance(plan,list): raise ValueError('邮件正文或AI拆分结果缺失')
    content_hash=hashlib.sha256((sender+'\n'+mail['sent_at']+'\n'+mail['body']).encode()).hexdigest()
    existing=[r for r in s.data['mail'] if r['邮件ID']==mid]
    if existing: return {'重复邮件':1}
    counts={'新增任务':0,'更新任务':0,'办结任务':0,'重新开启任务':0,'待确认':0,'旧反馈跳过':0}
    seen=set()
    for item in plan:
        snapshot=copy.deepcopy(s.data)
        try:
            if item.get('action')=='create':
                allowed=s.get_config('正式下达邮箱',[])
                quote=item.get('issuance_quote','')
                fields=item.get('fields',{})
                evidence=item.get('evidence',[])
                if sender.casefold() not in [x.casefold() for x in allowed]: raise ValueError('发件人未获管理员配置的正式下达权限')
                if not quote or quote not in mail['body'] or not re.search('下达|交办|督办',quote): raise ValueError('缺少明确正式下达原文')
                if not evidence or any(not e or e not in mail['body'] for e in evidence): raise ValueError('新增证据不可核对')
                if fields.get('主责部门','') not in quote or fields.get('任务名称','') not in quote or fields.get('原定截止日期','') not in quote: raise ValueError('任务定义、部门或明确截止日期不在下达原文')
                create(s,fields,'邮件:'+mid,mail['sent_at']); counts['新增任务']+=1
                continue
            t=match_feedback(s,item,sender,mail['sent_at'])
            if t['内部任务唯一ID'] in seen: raise ValueError('同邮件同任务多条结果，请合并字段后确认')
            evidence=item.get('evidence',[])
            if any(not isinstance(e,str) or not e or e not in mail['body'] for e in evidence): raise ValueError('证据不在邮件正文')
            anchors=item.get('anchors',[])
            # anchors为邮件原文与任务定义共有的业务锚点；多个相近候选同样命中时拒绝。
            if not anchors or any(not isinstance(a,str) or len(a)<2 or a not in mail['body'] or a not in t['任务名称']+' '+t['任务内容'] for a in anchors): raise ValueError('缺少跨正文和任务定义的业务锚点')
            peers=[x for x in all_tasks(s) if x['主责部门']==t['主责部门'] and all(a in x['任务名称']+' '+x['任务内容'] for a in anchors)]
            if len(peers)!=1: raise ValueError('业务锚点不能唯一定位任务')
            fields=item.get('fields',{})
            if fields.get('办理状态')=='已完成' and re.search(r'(未|尚未|没有|尚未全部)完成', ''.join(evidence)):
                raise ValueError('办结状态与原文未完成表述矛盾')
            # 完成百分比必须在本条原文中明确出现，不能模型估算。
            if '完成百分比' in fields:
                p=fields['完成百分比']; token=f'{p:g}%' if isinstance(p,(int,float)) else ''
                if not token or token not in ''.join(evidence).replace('％','%'): raise ValueError('原文未明确完成百分比')
            outcome=update(s,t['内部任务唯一ID'],fields,'邮件:'+mid,mail['sent_at'],False)
            seen.add(t['内部任务唯一ID'])
            key={'更新':'更新任务','办结':'办结任务','重新开启':'重新开启任务','旧反馈已跳过':'旧反馈跳过'}.get(outcome)
            if key: counts[key]+=1
        except Exception as e:
            s.data=snapshot
            s.pending('邮件反馈待确认',{'邮件ID':mid,'条目':item,'原因':str(e)})
            counts['待确认']+=1
    # 空计划只代表无相关事项，仍记录去重。保存失败则整个事务回滚，重跑同ID。
    s.data['mail'].append({'ID':uid(),'时间':now(),'邮件ID':mid,'状态':'含待确认' if counts['待确认'] else '已处理','内容':{'hash':content_hash,'摘要':counts}})
    return counts

def enqueue(s,recipient,level,body,key,tid='',attachments=None):
    if not EMAIL.fullmatch(recipient or ''):
        s.pending('缺少合法收件人',{'任务ID':tid,'等级':level}); return None
    if any(r['去重键']==key and r['状态'] not in ['已失效'] for r in s.data['outbox']): return None
    row={'ID':uid(),'时间':now(),'任务ID':tid,'接收人':recipient,'等级':level,'去重键':key,'状态':'待授权','尝试次数':0,
         '内容':{'subject':'督办通知｜'+level,'body':body,'attachments':attachments or []}}
    s.data['outbox'].append(row); return row['ID']

def warnings(s,today=None):
    today=today or datetime.now(TZ).date(); queued=[]
    for t in s.data['active']:
        d=(date.fromisoformat(t['原定截止日期'])-today).days
        levels=[]
        if d<0: levels.append('逾期督办')
        elif d in [7,3,1]: levels.append({7:'关注提醒',3:'临期预警',1:'紧急预警'}[d])
        # 以已入队/发送等级的最高值判定首次发现或升级；风险回落再升不重复通知相同等级。
        if t['当前AI风险等级'] in ['高','紧急']: levels.append('AI'+t['当前AI风险等级']+'风险')
        c=next(r for r in s.data['contacts'] if r['部门名称']==t['主责部门'])
        for level in levels:
            targets=[t['联系邮箱'] or c.get('主管邮箱','')]
            if level in ['紧急预警','逾期督办','AI高风险','AI紧急风险']: targets += [c.get('主管邮箱',''),c.get('管理员邮箱','')]
            for email in dict.fromkeys(targets):
                cycle=today.isoformat() if level=='逾期督办' else t['原定截止日期']
                key=f"{t['内部任务唯一ID']}|{t['重新开启次数']}|{level}|{cycle}|{email}"
                body='\n'.join([f'{k}：{t[k] or "未提供"}' for k in ['任务名称','主责部门','责任人','原定截止日期','预计完成日期','最新办理进展','当前AI风险等级','可能拖延原因','AI分析依据','AI整改建议']])
                body+='\nAI可能原因属于待核实研判。请反馈真实进展、阻塞事项及下一步计划。'
                q=enqueue(s,email,level,body,key,t['内部任务唯一ID'])
                if q: queued.append(q)
    return queued

def import_rows(s,rows,mapping):
    counts={'新增':0,'重复':0,'待确认':0}
    for index,row in enumerate(rows,2):
        snapshot=copy.deepcopy(s.data)
        try:
            fields={dst:row[src] for src,dst in mapping.items() if src in row and row[src] not in ('',None)}
            fields=validate(fields,True)
            exact=[t for t in all_tasks(s) if all(t.get(k,'')==fields.get(k,'') for k in ['任务名称','主责部门','原定截止日期','任务内容'])]
            if exact: counts['重复']+=1; continue
            peers=[t for t in all_tasks(s) if t['主责部门']==fields['主责部门'] and SequenceMatcher(None,t['任务名称'],fields['任务名称']).ratio()>=.55]
            if peers: raise ValueError('存在相近任务，需要语义复核，禁止直接覆盖')
            create(s,fields,'Excel导入'); counts['新增']+=1
        except Exception as e:
            s.data=snapshot; s.pending('Excel导入待确认',{'行':index,'原始数据':{k:str(v) for k,v in row.items()},'原因':str(e)})
            counts['待确认']+=1
    return counts
