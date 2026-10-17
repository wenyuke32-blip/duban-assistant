---
name: duban-watch
description: 使用MobileWork自身大模型分析督办事项，直接用自然语言调用cmcc-mail，持久化统一Excel台账，生成分级预警和四部门及管理员图表报告。
---

# 督办盯梢小助手 V1.2：MobileWork原生协作

面向广昌县分公司督办管理员，部门为市场部、政企部、网络部、综合部。

## 默认运行方式

**你就是MobileWork中的执行Agent：用你当前会话自身的大模型完成自然语言理解、任务匹配、拖延原因研判和报告复盘；直接以自然语言委托已安装的cmcc-mail查信、读信、取得附件、核验收件人和发送。不要要求用户另配模型API或编写Python邮箱/模型适配器。**

不需要先让用户提供cmcc-mail的接口文档才能开始。让cmcc-mail自己处理其认证、会话、企业通讯录和发送权限；遵循它运行时的实际指引。若平台能自动取得已安装Skill说明，可自行读取，不能把它变成默认阻塞条件。不能把联系人维护当成持续发送授权。

脚本仅负责字段和日期验证、任务增量持久化、确定性统计、去重、状态机和Excel/Word生成。JSON交接文件由你使用宿主文件能力在工作空间内部创建，**不要求管理员手工编写JSON、修改代码或安装新的AI服务**。

## 初次准备

1. 核实当前宿主可执行Python3.10+、依赖和中文字体、POSIX锁/原子替换/符号链接。可运行`python tools/check_environment.py`。不得假设平台允许安装依赖；不可执行时明确报告真实限制。
2. 固定同一个绝对持久化工作空间W；执行`python -m duban init --workspace W`。已有台账不覆盖。配置四部门主管及同一管理员的真实邮箱；不得猜邮箱。
3. 自然语言调用cmcc-mail，例如：“请搜索并读取新的督办反馈，提供稳定邮件引用、真实发件人、发送时间、正文和附件信息。”若需认证或确认，遵循该Skill的实际流程。不要伪造mobilework_auth_request参数或另建登录接口。

## 完整流程：持续执行到结束

所有命令从项目根目录执行，始终传`--workspace W`。过程文件放W中的内部交接目录，以UTF-8写入；不得包含认证凭据。用户只需说“执行完整督办流程”。

1. 执行`python -m duban full --workspace W`。默认进入原生协作；不传`--adapter`。返回run_id和当前stage。若上次未结束，恢复原run_id，不创建重复流程。
2. stage=sync：用自然语言调用cmcc-mail搜索、分页并读取新反馈。按上次同步时间适当重叠检索，首次范围由管理员实际资料确定。每封邮件由你按prompts/feedback.md分析，形成{run_id,source_skill:"cmcc-mail",mail:{id,sender,sent_at,body,attachments},plan:[…]}，调用`native-mail --file 文件`。信封身份取cmcc-mail真实结果，不能取正文自称。附件须先由cmcc-mail或平台合法下载到local_path，程序再真实提取。未能读取的附件不能说已读，不能结束完整同步。
3. 全部查询范围/分页处理完毕后，把实际查询结果摘要及邮件引用列表写为{run_id,source_skill:"cmcc-mail",complete:true,response_text:"cmcc-mail实际查询结果",observed_through:"可靠ISO时间",mail_ids:[…]}，调用`native-sync-finish --file 文件`。不能用未执行的拟查询或空模板冒充完成。
4. stage=analysis：执行`native-context`取最新任务、needs_analysis、expected_fingerprint和72小时历史。直接用你自己的大模型按prompts/analysis.md研判每个需分析任务，调用`native-analysis --file 文件`，输入为{run_id,task_id,expected_fingerprint,result:{…}}。不得编造百分比、日期、数量或不可查历史；事实与假设分开。脚本只校验并保存你的分析，不调用其他模型。
5. stage=report：对市场部、政企部、网络部、综合部、管理员综合分别执行`native-report-context --department 范围`。使用自身大模型按prompts/report.md撰写带任务ID与原文引用的复盘，调用`native-report-text --file 文件`。输入为{run_id,scope,expected_fingerprint,sections:[…]}。统计数字只来自返回的statistics；部门内容不能夹带其他部门专属事项。
6. stage=ready：执行`native-build`。程序校验同步、研判和五套复盘均已完成，生成预警队列及10份图表报告。相同日期同一业务快照复用报告，不重复入队；业务改变会要求重新分析或复盘。
7. stage=send：执行`native-next-send`。它先持久化发送中的关联标记，再返回**自然语言调用指令**、收件人、附件和handoff_id/request_digest。直接把该指令委托cmcc-mail执行；不要改收件人或附件。cmcc-mail自己核验通讯录并处理本次合法授权。若要求用户确认，按它的规则等待，不绕过。
8. 将cmcc-mail的真实回复写为{run_id,outbox_id,handoff_id,request_digest,source_skill:"cmcc-mail",outcome:"sent|not_sent|unknown|awaiting_confirmation",response_text:"实际回复",message_id?:"若平台确实返回"}，执行`native-send-result`。不要求平台必须返回消息ID；不能虚构一个。not_sent只有明确未被接受才能附definitely_not_accepted:true。拟发送/待确认/超时均不能标sent。
9. 重复第7–8步。若返回lookup_or_continue_original，**核实原调用或继续其授权对话，禁止再次发送**。已记成功的重复回执不会增加计数。未知结果保留，不能盲目重试。
10. stage=complete：根据native-context的实际summary输出邮件读取、新增更新、办结重开、报告、cmcc-mail明确返回成功、未知与待确认事项。Skill返回成功不等于收件箱送达证明。

完整输入结构、自然语言委托示例及恢复步骤见docs/MobileWork原生部署_V1.2.md和prompts/mobilework_native.md。

## 单项自然语言入口

| 管理员指令 | 你在后台执行 |
|---|---|
| 初始化督办系统 | init，配置真实联系人 |
| 导入督办台账 | 由自身大模型识别列映射，import；相近任务不直接覆盖 |
| 新增督办任务 / 更新督办进度 | context→自身理解→batch；缺字段或对象不唯一进待确认 |
| 同步督办邮件 | sync，按原生流程完成至同步结束 |
| 扫描督办风险 | scan，直接用自身模型研判；native-build结束扫描 |
| 执行督办预警 | warn，同步→自身研判→native-build→自然语言委托cmcc-mail |
| 生成部门周报 / 生成综合报告 | native-start --intent reports→自身研判及五套复盘→native-build；仅生成，不发送 |
| 发送部门周报 | send-reports入队→native-start --intent send→native-next-send→委托cmcc-mail→回写 |
| 查询督办任务 | query，支持--department及--risk |
| 查看待确认事项 | pending，管理员核实后resolve |
| 执行完整督办流程 | full，按上述原生流程持续执行 |

close/reopen/delete仅在管理员明确请求且ID唯一时执行。主管邮件不允许物理删除、修改联系人或原截止日期。预计完成日期与原截止日期分开。已归档明确未完成才重开同一ID。未提供完成百分比不生成数字。多任务邮件拆分，唯一性和证据不足时待确认，不只看模型自报置信度。

## 数据与发送保护

统一文件固定为督办管理总台账.xlsx；安全写入、上一有效备份、发布日志、72小时事件记录和累计统计由脚本维护。recover用于管理员显式恢复，恢复可能回退发送记录，必须先核实已发送结果。报告仅保留最新10件；部门主管仅收到本部门两件，管理员综合仅给管理员。

默认不用Python适配器。旧版--adapter仅为可选兼容入口，不是使用本Skill的前置条件。此交付的本地模拟回执测试不等于已经在MobileWork或企业邮箱实测；实际运行后据真实结果更新验收。
