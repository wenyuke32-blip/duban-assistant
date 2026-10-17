"""无--adapter的原生协作CLI验收。AI/邮件回执为脚本化模拟，不访问真实服务。"""
import argparse,json,subprocess,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from docx import Document
PROJECT=Path(__file__).resolve().parents[1];TZ=timezone(timedelta(hours=8))

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output).resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit('验收目录必须为空')
 out.mkdir(parents=True,exist_ok=True);ws=out/'workspace';trace=[];n=0
 def call(command,payload=None,*extra):
  nonlocal n
  args=[sys.executable,'-m','duban',command,'--workspace',str(ws),*extra]
  if payload is not None:
   f=out/'input.json';f.write_text(json.dumps(payload,ensure_ascii=False));args+=['--file',str(f)]
  proc=subprocess.run(args,cwd=PROJECT,capture_output=True,text=True);assert proc.returncode==0,proc.stdout+proc.stderr
  value=json.loads(proc.stdout);trace.append({'command':command,'result':value});n+=1;return value['结果']
 for i,d in enumerate(['市场部','政企部','网络部','综合部']):
  call('contacts',{'部门名称':d,'主管邮箱':f'd{i}@example.invalid','管理员邮箱':'admin@example.invalid'})
  call('add',{'任务名称':'测试原生'+d+'交付','主责部门':d,'原定截止日期':(datetime.now(TZ).date()+timedelta(days=3)).isoformat(),'最新办理进展':'测试初始进展'})
 c=call('native-start',None,'--simulation');rid=c['run_id'];t=next(t for t in c['tasks'] if t['主责部门']=='政企部');body=t['任务名称']+'资源不足'
 payload={'run_id':rid,'source_skill':'cmcc-mail','mail':{'id':'SIM-NATIVE-1','sender':'d1@example.invalid','sent_at':datetime.now(TZ).isoformat(),'body':body},'plan':[{'action':'update','task_id':t['内部任务唯一ID'],'candidate_ids':[t['内部任务唯一ID']],'evidence':[body],'anchors':[t['任务名称']],'fields':{'办理状态':'受阻','最新办理进展':'资源不足'}}]}
 assert call('native-mail',payload)['更新任务']==1
 assert call('native-mail',payload)['重复邮件']==1
 c=call('native-sync-finish',{'run_id':rid,'source_skill':'cmcc-mail','complete':True,'response_text':'模拟搜索结果：完整范围1封邮件','mail_ids':['SIM-NATIVE-1'],'observed_through':datetime.now(TZ).isoformat()})
 for t in c['tasks']:
  if not t['needs_analysis']:continue
  q=t['最新办理进展'];result={'risk':'高' if q=='资源不足' else '低','facts':[q],'hypotheses':['脚本化模拟：资源依赖待核实'],'evidence':[q],'actions':['脚本化模拟建议：确认交付安排'],'coordination':['网络部'] if q=='资源不足' else [],'category':'资源依赖' if q=='资源不足' else '信息不足','next_focus':['脚本化模拟：下次反馈']}
  call('native-analysis',{'run_id':rid,'task_id':t['内部任务唯一ID'],'expected_fingerprint':t['expected_fingerprint'],'result':result})
 for scope in ['市场部','政企部','网络部','综合部','管理员综合']:
  rc=call('native-report-context',None,'--department',scope);t=rc['tasks'][0]
  call('native-report-text',{'run_id':rid,'scope':scope,'expected_fingerprint':rc['expected_fingerprint'],'sections':[{'heading':'主要进展','text':'脚本化模拟复盘：'+t['任务名称']+'；'+t['最新办理进展'],'task_ids':[t['内部任务唯一ID']],'evidence':[{'task_id':t['内部任务唯一ID'],'quote':t['最新办理进展']}]}]})
 call('native-build');sent=0;first=None
 while True:
  h=call('native-next-send')
  if h.get('stage')=='complete':break
  assert h['action']=='call_cmcc_mail'
  receipt={k:h[k] for k in ['run_id','handoff_id','outbox_id','request_digest']}|{'source_skill':'cmcc-mail','outcome':'sent','response_text':'模拟cmcc-mail回复：发送成功；未调用真实邮箱'}
  if first is None:
   first=receipt;unknown=dict(receipt,outcome='unknown',response_text='模拟超时，结果未知')
   call('native-send-result',unknown);query=call('native-next-send');assert query['action']=='lookup_or_continue_original' and query['handoff_id']==h['handoff_id']
  call('native-send-result',receipt);sent+=1
 assert call('native-send-result',first)['重复回执'] is True
 summary=call('native-context')['summary'];assert summary['模拟发送数']==sent and summary['cmcc_mail明确返回成功数']==0
 assert len(list((ws/'reports').iterdir()))==10
 for scope in ['市场部','政企部','网络部','综合部','管理员综合']:
  doc=Document(ws/'reports'/(scope+'督办报告.docx'));assert '脚本化模拟复盘' in '\n'.join(p.text for p in doc.paragraphs)
 # 同一快照重跑：同步空结果后复用现有有效研判/复盘和报告，不重新发送。
 again=call('native-start',None,'--simulation');rid2=again['run_id']
 c=call('native-sync-finish',{'run_id':rid2,'source_skill':'cmcc-mail','complete':True,'response_text':'模拟查询：无新增反馈','mail_ids':[],'observed_through':datetime.now(TZ).isoformat()});assert c['stage']=='ready'
 call('native-build');done=call('native-next-send');assert done['stage']=='complete' and done['summary']['模拟发送数']==0
 result={'CLI_calls':n,'custom_adapter_used':False,'native_stages_completed':True,'report_files':10,'narrative_in_Word':True,'duplicate_mail_and_receipt_idempotent':True,'unknown_result_queries_original':True,'repeat_run_additional_sends':0,'simulated_receipts':sent,'real_mail_calls':0,'real_model_calls':0,'scope':'本地真实CLI/文件状态机；模型与cmcc-mail自然语言回复均由脚本模拟'}
 (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(out/'trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
