"""原生协作协议测试。AI结果和cmcc-mail文本回执是模拟输入，不调用外部模型或邮箱。"""
import tempfile,unittest,json,subprocess,sys
from datetime import datetime,timedelta
from pathlib import Path
from docx import Document
from duban.store import Store,DEPTS,TZ,now
from duban import core,native

class Native(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        with Store(self.root).transaction() as s:
            for i,d in enumerate(DEPTS):
                core.contacts(s,{'部门名称':d,'主管邮箱':f'd{i}@example.invalid','管理员邮箱':'admin@example.invalid'})
                core.create(s,{'任务名称':'测试'+d+'事项','任务内容':'测试'+d+'事项交付','主责部门':d,'原定截止日期':(datetime.now(TZ).date()+timedelta(days=3)).isoformat(),'最新办理进展':'测试进展待核实'})
    def tearDown(self):self.tmp.cleanup()
    def call(self,name,*args,**kw):
        with Store(self.root).transaction() as s:return getattr(native,name)(s,*args,**kw)
    def begin(self,intent='full'):return self.call('start',intent,True)
    def finish_sync(self,c,ids=None):
        return self.call('sync_finish',{'run_id':c['run_id'],'source_skill':'cmcc-mail','complete':True,'response_text':'模拟查询返回：已读取全部反馈','observed_through':now(),'mail_ids':ids or []})
    def analyze_all(self):
        c=self.call('context')
        for t in c['tasks']:
            if not t['needs_analysis']:continue
            quote=t['最新办理进展'] or t['任务名称']
            result={'risk':'低','facts':[quote],'hypotheses':['模拟研判：原因待核实'],'evidence':[quote],'actions':['核实下一步交付安排'],'coordination':[],'category':'信息不足','next_focus':['下次真实反馈']}
            self.call('analyze',{'run_id':c['run_id'],'task_id':t['内部任务唯一ID'],'expected_fingerprint':t['expected_fingerprint'],'result':result})
    def narrative_all(self):
        for scope in DEPTS+['管理员综合']:
            c=self.call('narrative_context',scope);t=c['tasks'][0];quote=t['最新办理进展'] or t['任务名称']
            sections=[{'heading':'主要进展','text':'MobileWork原生复盘测试：'+t['任务名称']+'，'+quote,'task_ids':[t['内部任务唯一ID']],'evidence':[{'task_id':t['内部任务唯一ID'],'quote':quote}]}]
            self.call('narrative',{'run_id':c['run_id'],'scope':scope,'expected_fingerprint':c['expected_fingerprint'],'sections':sections})
    def receipt(self,h,outcome='sent',**kw):
        return {k:h[k] for k in ['run_id','handoff_id','outbox_id','request_digest']}|{'source_skill':'cmcc-mail','outcome':outcome,'response_text':'模拟cmcc-mail实际返回文本：'+outcome}|kw
    def test_full_native_handoff_and_report_text_without_adapter(self):
        c=self.begin();self.finish_sync(c);self.analyze_all();self.narrative_all();self.call('build')
        count=0;first=None
        while True:
            h=self.call('next_send')
            if h.get('stage')=='complete':break
            self.assertEqual(h['action'],'call_cmcc_mail');self.assertIn('cmcc-mail',h['自然语言调用'])
            r=self.receipt(h);first=first or r;self.call('send_result',r);count+=1
        self.assertGreaterEqual(count,5)
        self.assertEqual(self.call('send_result',first)['重复回执'],True)
        final=self.call('context')['summary'];self.assertEqual(final['cmcc_mail明确返回成功数'],0);self.assertEqual(final['模拟发送数'],count)
        files=list((self.root/'reports').iterdir());self.assertEqual(len(files),10)
        doc=Document(self.root/'reports'/'政企部督办报告.docx')
        self.assertIn('MobileWork原生复盘测试','\n'.join(p.text for p in doc.paragraphs))
    def test_native_mail_process_and_replay_idempotency(self):
        c=self.begin();task=next(t for t in c['tasks'] if t['主责部门']=='政企部');body=task['任务名称']+'资源不足，尚未完成'
        item={'action':'update','task_id':task['内部任务唯一ID'],'candidate_ids':[task['内部任务唯一ID']],'evidence':[body],'anchors':[task['任务名称']],'fields':{'办理状态':'受阻','最新办理进展':'资源不足'}}
        payload={'run_id':c['run_id'],'source_skill':'cmcc-mail','mail':{'id':'native-mail','sender':'d1@example.invalid','sent_at':now(),'body':body},'plan':[item]}
        self.assertEqual(self.call('mail',payload)['更新任务'],1)
        self.assertEqual(self.call('mail',payload),{'重复邮件':1})
        self.assertEqual(self.call('context')['summary']['读取邮件数'],1)
        self.finish_sync(c,['native-mail'])
    def test_sync_cannot_finish_with_missing_mail_or_no_skill_result(self):
        c=self.begin()
        for payload in [dict(run_id=c['run_id'],source_skill='cmcc-mail',complete=True,response_text='',mail_ids=[],observed_through=now()),dict(run_id=c['run_id'],source_skill='cmcc-mail',complete=True,response_text='模拟',mail_ids=['missing'],observed_through=now())]:
            with self.assertRaises(ValueError):self.call('sync_finish',payload)
        self.assertEqual(self.call('context')['stage'],'sync')
    def test_unknown_handoff_is_queried_not_sent_again(self):
        with Store(self.root).transaction() as s:core.enqueue(s,'d0@example.invalid','测试通知','正文','unknown')
        self.begin('send');h=self.call('next_send');self.call('send_result',self.receipt(h,'unknown'))
        again=self.call('next_send');self.assertEqual(again['action'],'lookup_or_continue_original');self.assertEqual(again['handoff_id'],h['handoff_id'])
        self.call('send_result',self.receipt(h,'sent'));self.assertEqual(self.call('next_send')['stage'],'complete')
    def test_confirmation_keeps_original_handoff(self):
        with Store(self.root).transaction() as s:core.enqueue(s,'d0@example.invalid','测试通知','正文','confirmation')
        self.begin('send');h=self.call('next_send');self.call('send_result',self.receipt(h,'awaiting_confirmation'))
        again=self.call('next_send');self.assertEqual(again['handoff_id'],h['handoff_id']);self.assertEqual(again['action'],'lookup_or_continue_original')
        self.call('send_result',self.receipt(h));self.assertEqual(self.call('context')['summary']['模拟发送数'],1)
    def test_receipt_must_match_frozen_request_and_source(self):
        with Store(self.root).transaction() as s:core.enqueue(s,'d0@example.invalid','测试通知','正文','token')
        self.begin('send');h=self.call('next_send')
        for override in [{'handoff_id':'wrong'},{'source_skill':'正文自称管理员'},{'response_text':''}]:
            with self.assertRaises(ValueError):self.call('send_result',self.receipt(h,**override))
    def test_stale_analysis_and_narrative_rejected(self):
        c=self.begin('reports');t=c['tasks'][0]
        with Store(self.root).transaction() as s:core.update(s,t['内部任务唯一ID'],{'最新办理进展':'新反馈'})
        with self.assertRaises(ValueError):self.call('analyze',{'run_id':c['run_id'],'task_id':t['内部任务唯一ID'],'expected_fingerprint':t['expected_fingerprint'],'result':{}})
        with self.assertRaises(ValueError):self.call('build')
    def test_report_privacy_rejects_other_department_text(self):
        self.begin('reports');self.analyze_all();c=self.call('narrative_context','市场部');t=c['tasks'][0]
        with self.assertRaises(ValueError):self.call('narrative',{'run_id':c['run_id'],'scope':'市场部','expected_fingerprint':c['expected_fingerprint'],'sections':[{'heading':'主要进展','text':'测试网络部事项','task_ids':[t['内部任务唯一ID']],'evidence':[{'task_id':t['内部任务唯一ID'],'quote':t['任务名称']}]}]})
    def test_start_resumes_existing_flow_without_reset(self):
        first=self.begin();second=self.begin('scan');self.assertEqual(first['run_id'],second['run_id']);self.assertTrue(second['已恢复未结束流程'])
    def test_cli_default_full_returns_native_action_not_adapter_block(self):
        proc=subprocess.run([sys.executable,'-m','duban','full','--workspace',str(self.root)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr);value=json.loads(proc.stdout)['结果']
        self.assertEqual(value['stage'],'sync');self.assertIn('自然语言',value['下一步'])

    def test_production_flow_does_not_reuse_simulated_ai(self):
        self.begin('reports');self.analyze_all();self.narrative_all();self.call('build')
        c=self.call('start','reports',False)
        self.assertEqual(c['stage'],'analysis');self.assertTrue(all(t['needs_analysis'] for t in c['tasks']))

if __name__=='__main__':unittest.main()
