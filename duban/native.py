"""MobileWork原生编排：宿主自身推理，以自然语言委托cmcc-mail。
这里只保存宿主的结构化结果和真实Skill回执，不连接另一个模型/邮箱API。
"""
import copy,hashlib,json
from datetime import datetime,date,timedelta
from pathlib import Path
from .store import DEPTS,TZ,now,uid,stamp
from . import core
from .reports import generate,queue_reports,business_report_fingerprint,report_fingerprint,_manifest_valid,save_narrative,report_context

SCOPES=DEPTS+['管理员综合']

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def current(s,run_id=None):
    r=copy.deepcopy(s.get_config('native_run'))
    if not r or (run_id and r['id']!=run_id):raise ValueError('原生协作流程不存在或run_id不符')
    return r

def put(s,r):s.set_config('native_run',r)
def mode(r):return 'simulation' if r['simulation'] else 'production'

def advance(s,r):
    if r['stage'] in ['analysis','report','ready']:
        active={t['内部任务唯一ID']:t for t in s.data['active']}
        remaining=set(r.get('analysis_remaining',[]))&set(active)
        remaining.update(tid for tid,t in active.items() if not core.current_analysis(s,t) or s.get_config('analysis_meta:'+tid,{}).get('execution_mode')!=mode(r))
        r['analysis_remaining']=sorted(remaining)
        if remaining:r['stage']='analysis'
        elif r['intent'] in ['full','reports']:
            fp=business_report_fingerprint(s)
            r['stage']='ready' if all(s.get_config('narrative:'+scope,{}).get('fingerprint')==fp and s.get_config('narrative:'+scope,{}).get('execution_mode')==mode(r) for scope in SCOPES) else 'report'
        else:r['stage']='ready'
    put(s,r)

def start(s,intent='full',simulation=False):
    if intent not in ['full','sync','scan','warn','reports','send']:raise ValueError('原生流程intent无效')
    old=s.get_config('native_run')
    if old and old['stage']!='complete':return {'已恢复未结束流程':True,**context(s)}
    r={'id':uid(),'intent':intent,'simulation':simulation,'stage':('send' if intent=='send' else 'sync' if intent in ['full','sync','warn'] else 'analysis'),
       'started_at':now(),'read_count':0,'counts':{},'accepted_by_skill':0,'simulation_sends':0,'reports':[],'handoff':None}
    required=[]
    for t in s.data['active']:
        last=t.get('最新AI研判时间');days=(date.fromisoformat(t['原定截止日期'])-datetime.now(TZ).date()).days
        if intent=='scan' or not core.current_analysis(s,t) or not last or datetime.now(TZ)-stamp(last)>=timedelta(days=7) or (days<=7 and stamp(last).date()<datetime.now(TZ).date()):required.append(t['内部任务唯一ID'])
    r['analysis_remaining']=required
    put(s,r);advance(s,r);return context(s)

def context(s):
    r=current(s);advance(s,r)
    tasks=copy.deepcopy(core.all_tasks(s))
    for t in tasks:
        t['expected_fingerprint']=core.task_fingerprint(t);t['needs_analysis']=t['内部任务唯一ID'] in r.get('analysis_remaining',[])
    instructions={
      'sync':'直接用自然语言调用cmcc-mail搜索新反馈并读取详情/合法下载附件，宿主自行分析后逐封native-mail；完整分页后native-sync-finish。',
      'analysis':'使用MobileWork当前会话自身大模型，按prompts/analysis.md逐任务研判后native-analysis，不需要另配API或Python模型模块。',
      'report':'使用MobileWork自身大模型，native-report-context取得各部门真实统计和证据，撰写带任务引用的复盘后native-report-text。',
      'ready':'执行native-build，程序校验研判、统计并生成预警队列/10份报告。',
      'send':'执行native-next-send；按返回的自然语言指令直接调用cmcc-mail；以其实际返回记录native-send-result，禁止虚构成功。',
      'complete':'流程结束，输出summary；实际收到邮件仍需收件箱证据。'}
    return {'run_id':r['id'],'intent':r['intent'],'stage':r['stage'],'simulation':r['simulation'],'下一步':instructions[r['stage']],
      'sync_since':s.get_config('native_sync_checkpoint'),'tasks':tasks,'contacts':copy.deepcopy(s.data['contacts']),
      'history_72h':copy.deepcopy(s.data['history']),'summary':summary(s,r)}

def summary(s,r=None):
    r=r or current(s)
    return {'读取邮件数':r['read_count'],**r['counts'],'cmcc_mail明确返回成功数':r['accepted_by_skill'],
      '模拟发送数':r['simulation_sends'],'真实收件箱投递验证':'未由本内核执行','报告文件数':len(r['reports']),
      '未确认发送结果数':sum(x['状态'] in ['发送中','结果未知'] for x in s.data['outbox']),
      '待确认事项数':sum(x['状态']=='待确认' for x in s.data['pending']),
      '来源':'模拟数据' if r['simulation'] else 'MobileWork原生会话与cmcc-mail返回；由宿主保存原始结果，本内核不提供平台签名证明'}

def mail(s,payload):
    r=current(s,payload['run_id'])
    if r['stage']!='sync':raise ValueError('当前不在邮件同步阶段')
    if payload.get('source_skill')!='cmcc-mail':raise ValueError('必须来自cmcc-mail的实际调用')
    m=copy.deepcopy(payload['mail']);mid=m['id']
    existing=next((x for x in s.data['mail'] if x['邮件ID']==mid),None)
    if existing:
        if existing['内容'].get('native_last_read_run')!=r['id']:r['read_count']+=1
        existing['内容']['native_last_read_run']=r['id'];put(s,r)
        return {'重复邮件':1}
    from .__main__ import extract
    sources={'body':m.get('body','')};digests={}
    for i,a in enumerate(m.get('attachments',[])):
        p=Path(a.get('local_path',''))
        if not p.is_file() or p.stat().st_size>16*1024*1024:raise ValueError('附件未由cmcc-mail/平台合法下载或超过16MiB')
        value=extract(p);key='attachment:'+str(i)
        sources[key]=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
        digests[key]=hashlib.sha256(p.read_bytes()).hexdigest()
    m['evidence_sources']=sources;m['attachment_digests']=digests
    result=core.process_mail(s,m,payload['plan'])
    row=next(x for x in s.data['mail'] if x['邮件ID']==mid);row['内容']['native_last_read_run']=r['id']
    r['read_count']+=1
    for k,v in result.items():r['counts'][k]=r['counts'].get(k,0)+v
    put(s,r);return result

def sync_finish(s,payload):
    r=current(s,payload['run_id'])
    if r['stage']!='sync':return {'已结束同步':True,'stage':r['stage']}
    if payload.get('source_skill')!='cmcc-mail' or payload.get('complete') is not True or not str(payload.get('response_text','')).strip():
        raise ValueError('必须有cmcc-mail实际查询结果，并确认已读取完整范围/分页')
    ids=payload.get('mail_ids')
    if not isinstance(ids,list) or any(not any(row['邮件ID']==mid for row in s.data['mail']) for mid in ids):raise ValueError('查询返回的邮件尚未全部写入处理记录')
    through=payload['observed_through'];stamp(through)
    r['sync_result']={'source_skill':'cmcc-mail','complete':True,'response_digest':digest(payload['response_text']),'observed_through':through}
    s.set_config('native_sync_checkpoint',through)
    r['stage']='complete' if r['intent']=='sync' else 'analysis';advance(s,r);return context(s)

def analyze(s,payload):
    r=current(s,payload['run_id'])
    if r['stage'] not in ['analysis','report','ready']:raise ValueError('当前不在AI研判阶段')
    t=core.find(s,payload['task_id'])
    if payload.get('expected_fingerprint')!=core.task_fingerprint(t):raise ValueError('研判期间任务已变化，请重新读取原文')
    core.apply_analysis(s,t['内部任务唯一ID'],payload['result'],mode(r))
    meta=s.get_config('analysis_meta:'+t['内部任务唯一ID']);meta['origin']='MobileWork自身大模型（宿主声明）'
    s.set_config('analysis_meta:'+t['内部任务唯一ID'],meta)
    r['analysis_remaining']=[tid for tid in r.get('analysis_remaining',[]) if tid!=t['内部任务唯一ID']];advance(s,r)
    return {'task_id':t['内部任务唯一ID'],'stage':r['stage']}

def narrative_context(s,scope):
    r=current(s);advance(s,r)
    if scope not in SCOPES:raise ValueError('报告范围无效')
    return {'run_id':r['id'],**report_context(s,scope)}

def narrative(s,payload):
    r=current(s,payload['run_id'])
    if r['stage'] not in ['report','ready']:raise ValueError('当前不在报告分析阶段')
    save_narrative(s,payload['scope'],payload['sections'],payload['expected_fingerprint'],mode(r));advance(s,r)
    return {'scope':payload['scope'],'stage':r['stage']}

def build(s):
    r=current(s);advance(s,r)
    if r['stage'] in ['send','complete']:return context(s)
    if r['stage']!='ready':raise ValueError('尚未完成原生邮件同步、任务研判或报告复盘，先native-context继续')
    if r['intent'] in ['full','warn']:core.warnings(s)
    if r['intent'] in ['full','reports']:
        r['reports']=generate(s)
        if r['intent']=='full':queue_reports(s)
    r['stage']='send' if r['intent'] in ['full','warn'] else 'complete';put(s,r)
    return context(s)

def _row(s,oid):
    return next((x for x in s.data['outbox'] if x['ID']==oid),None)

def _valid_outbox(s,row):
    if str(row['等级']).endswith('报告'):
        info=s.get_config('reports',{})
        if info.get('fingerprint')!=report_fingerprint(s) or not _manifest_valid(s,info):return False
    return all(Path(a['path']).is_file() and hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()==a['sha256'] for a in row['内容']['attachments'])

def next_send(s):
    r=current(s)
    if r['stage']!='send':return context(s)
    if r.get('handoff'):
        h=r['handoff'];row=_row(s,h['outbox_id'])
        if row and row['状态'] in ['发送中','结果未知','待授权']:
            return {'run_id':r['id'],**h,'action':'lookup_or_continue_original',
              '自然语言调用':'请cmcc-mail核实原调用的授权/发送结果；不要再次发送。关联标记DUBAN-'+row['ID']+'，收件人'+row['接收人']+'，主题'+row['内容']['subject']+'。明确区分已发送、明确未接受和未知；需要确认时遵守你自身规则。'}
        r['handoff']=None
    # 前一进程/流程留下未知项时先核实，绝不因重新开始流程重发。
    unknown=next((x for x in s.data['outbox'] if x['状态'] in ['发送中','结果未知']),None)
    if unknown:
        h=unknown['内容'].get('native_handoff') or {'handoff_id':uid(),'outbox_id':unknown['ID'],'request_digest':digest({k:unknown[k] for k in ['接收人','等级','任务ID']})}
        unknown['内容']['native_handoff']=h;r['handoff']=h;put(s,r);return next_send(s)
    for row in s.data['outbox']:
        if row['状态'] not in ['待授权','失败'] or int(row['尝试次数'] or 0)>=3:continue
        if not _valid_outbox(s,row):row['状态']='已失效';continue
        h={'handoff_id':uid(),'outbox_id':row['ID'],'request_digest':digest({'recipient':row['接收人'],'payload':row['内容']})}
        row['状态']='发送中';row['尝试次数']=int(row['尝试次数'] or 0)+1;row['内容']['native_handoff']=h;r['handoff']=h;put(s,r)
        data=row['内容'];attachments=data['attachments']
        text='请调用cmcc-mail发送此督办邮件。由cmcc-mail按自身规范验证企业通讯录，并处理用户确认或正式预授权；无授权则不要发送。'
        text+='\n收件人：'+row['接收人']+'\n主题：'+data['subject']+' [DUBAN-'+row['ID']+']\n正文：'+data['body']
        text+='\n附件：'+('、'.join(a['path'] for a in attachments) or '无')+'\n请返回实际执行结果；不要把拟发送、待确认或未知说成成功。'
        return {'run_id':r['id'],**h,'action':'call_cmcc_mail','recipient':row['接收人'],'subject':data['subject'],'attachments':attachments,'自然语言调用':text}
    r['stage']='complete';r['handoff']=None;put(s,r);return context(s)

def send_result(s,payload):
    r=current(s,payload['run_id']);row=_row(s,payload['outbox_id'])
    if not row:raise ValueError('待发送项不存在')
    h=row['内容'].get('native_handoff',{})
    if payload.get('handoff_id')!=h.get('handoff_id') or payload.get('request_digest')!=h.get('request_digest'):raise ValueError('回执与原生调用快照不匹配')
    if payload.get('source_skill')!='cmcc-mail' or not isinstance(payload.get('response_text'),str) or not payload['response_text'].strip():raise ValueError('必须记录cmcc-mail真实返回，不能用拟发送文本充当回执')
    outcome=payload.get('outcome')
    if outcome not in ['sent','not_sent','unknown','awaiting_confirmation']:raise ValueError('回执状态无效')
    if row['状态']=='已发送':return {'重复回执':True,'状态':'已发送'}
    if row['状态'] not in ['发送中','结果未知','待授权']:raise ValueError('当前项没有正在等待的原生调用')
    receipt={'source_skill':'cmcc-mail','response_text':payload['response_text'][:6000],'response_sha256':digest(payload['response_text']),'execution_mode':mode(r),'时间':now()}
    if payload.get('message_id'):receipt['message_id']=str(payload['message_id']) # 不伪造平台ID
    if outcome=='sent':
        row['状态']='已发送';row['内容']['发送凭据']=receipt
        if r['simulation']:r['simulation_sends']+=1
        else:r['accepted_by_skill']+=1
        for t in core.all_tasks(s):
            if t['内部任务唯一ID']==row['任务ID']:t['最近邮件通知时间']=now();t['最近通知等级']=row['等级']
        r['handoff']=None
    elif outcome=='awaiting_confirmation':row['状态']='待授权';row['内容']['原生调用反馈']=receipt
    elif outcome=='not_sent' and payload.get('definitely_not_accepted') is True:
        row['状态']='失败';row['内容']['原生调用反馈']=receipt;r['handoff']=None
    else:row['状态']='结果未知';row['内容']['原生调用反馈']=receipt
    put(s,r);return {'状态':row['状态'],'summary':summary(s,r)}
