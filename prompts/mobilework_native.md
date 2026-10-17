# 原生协作执行约定

由MobileWork当前会话自身大模型完成理解和研判，以自然语言委托cmcc-mail。无额外模型API、邮箱HTTP端点或必须编写的Python桥接模块。

native-context返回当前stage：sync→analysis→report→ready→send→complete。脚本保存检查点。每次先取得当前run_id；中断后native-context继续，不重置台账或发送状态。start遇到未结束流程恢复原流程。

- sync：cmcc-mail实际查信；邮件按feedback.md形成native-mail输入。附件先真实下载，不能把附件内容冒充正文。最后完整范围/分页确实处理完才native-sync-finish。
- analysis：读取needs_analysis=true的任务，按analysis.md自行研判，保留expected_fingerprint；输入给native-analysis。任务变化则重新读取，不强行写入旧结论。
- report：对五个范围读取native-report-context，按report.md自行写复盘并native-report-text。数字由程序提供，引用本范围的真实任务。
- ready：native-build校验后生成队列/10份文件。
- send：native-next-send返回自然语言指令后直接委托cmcc-mail，保存实际回复后native-send-result。
- complete：输出summary，只报实际执行记录。需要授权或结果未知可暂停，不能为追求complete而虚构结果。

outcome=sent只在cmcc-mail明确报告实际发送成功时使用；awaiting_confirmation保存并继续原Skill的授权对话；not_sent须有明确未接受依据；其余unknown。重复native-next-send会先要求核实原调用，不是重新发信。request_digest/handoff_id由程序给出，宿主原样回写；它们是内部去重标记，不是cmcc-mail认证凭据或平台签名。

测试时native-start --simulation可明确标记模拟输入，发送计入模拟计数，不计cmcc-mail真实成功。生产不要用该参数。此标记不创造或验证任何平台授权；原始来源真实性由运行中的MobileWork会话负责，脚本不能从手填JSON证明平台确实执行。

用户只说自然语言，JSON与脚本命令由你在内部完成，不把技术交接步骤推给用户。
