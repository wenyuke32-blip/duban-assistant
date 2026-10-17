# MobileWork原生部署与操作 V1.2

本版按MobileWork自身具备大模型、可用自然语言调用cmcc-mail的方式运行。不另外配置模型API，不开发邮箱HTTP接口，不要求先编写Python适配模块。

## 管理员需要做的事

1. 下载V1.2压缩包并解压，将完整项目通过MobileWork现有Skill安装/导入方式加入，保留SKILL.md、duban、prompts等相对目录。当前包是源码Skill项目，不冒称经过平台验证的签名安装包。
2. 让MobileWork读取SKILL.md，核实宿主可以执行项目脚本及读写固定持久化目录。依赖见requirements.txt；需Python3.10+、POSIX锁/原子替换/符号链接、中文字体。先运行tools/check_environment.py；平台未允许安装时不擅自安装。
3. 对助手说：“初始化督办系统。固定台账保存在〔你的持久化目录〕，四部门主管和管理员邮箱分别是〔真实资料〕。”已有台账只读取，不覆盖；若已有Excel则上传并说“导入督办台账”。
4. 日常直接说“同步督办邮件”“扫描督办风险”“生成部门周报”或“执行完整督办流程”。AI推理、JSON交接和脚本命令都由MobileWork在后台完成，管理员不手写JSON、不改代码。
5. cmcc-mail如需认证或发送确认，按它自身的实际指引操作。不能因为配置了联系人就假设所有未来邮件已授权。

**不需要把cmcc-mail的SKILL.md/API参数交给本项目作为运行前置条件。** 可直接自然语言委托它，让它负责合法认证、会话与收发规范。这里仍没有证明当前聊天已进入MobileWork或实际调用了你的企业邮箱；真实验收应在你的MobileWork环境运行。

## 实际分工

| 工作 | 执行者 |
|---|---|
| 管理员自然语言、邮件语义、唯一候选、拖延原因与整改措施 | MobileWork当前会话自身的大模型 |
| 搜索/读取邮件、合法取得附件、企业通讯录、发送和已发送核实 | 直接自然语言调用cmcc-mail，由该Skill自行执行 |
| 日期/字段验证、任务持久化与归档重开、统计、去重、恢复 | Python业务内核 |
| 正式复盘段落 | MobileWork自身大模型基于真实统计/任务证据撰写 |
| 10份Excel/Word图表与复盘内容排版 | 内核实际生成并安全替换文件 |

## 后台执行顺序（供Skill执行者核对）

```bash
python -m duban full --workspace W
python -m duban native-context --workspace W
```

full默认返回原生阶段，宿主Agent持续按SKILL.md执行，直到完成或因cmcc-mail确认/未知结果暂停。单个Linux进程不会自行启动MobileWork或伪装成模型；MobileWork当前Agent是编排执行者。

阶段和交接入口：

| 阶段 | 宿主动作 | 校验/持久化入口 |
|---|---|---|
| sync | 自然语言让cmcc-mail查新邮件、读详情、下载附件；自己拆分/匹配 | native-mail；全部实际完成后native-sync-finish |
| analysis | 读取needs_analysis=true的任务，用自身大模型研判 | native-analysis，核对原任务指纹 |
| report | 分五个范围读取真实统计与证据，用自身模型复盘 | native-report-context → native-report-text |
| ready | 让程序生成预警及10份报告 | native-build |
| send | 使用程序返回的精确自然语言委托调用cmcc-mail | native-next-send → native-send-result |
| complete | 根据持久化summary回复管理员 | native-context |

输入格式见SKILL.md、prompts/mobilework_native.md。MobileWork使用自己的文件能力写UTF-8交接文件，脚本以--file读取；不要拼接邮件正文进Shell，不把认证令牌写入交接文件、台账或日志。

## 自然语言委托示例

“请cmcc-mail搜索和读取最近一次督办同步以来的新反馈，并适当重叠检索；返回邮件引用、真实发件人、发送时间、完整正文及附件，分页要继续读取。需要认证时按你自身的规范处理。”

发送时直接使用native-next-send返回的自然语言调用。它含精确收件人、主题、正文、文件路径和DUBAN关联标记。cmcc-mail自己核验通讯录与本次授权。需要确认时继续原Skill对话，不重新发起相同发送。

回执不必强行有消息ID：真实返回有message_id才保存；没有就保存实际操作结果文本及内部摘要，不把内部摘要冒充平台ID。只保存邮件操作结果，绝不复制认证凭据。拟发送、待确认、超时/未知都不能说成功。成功仅表示cmcc-mail明确报告已发送，收件箱投递是另一项验证。

## 中断、重复调用与异常

- 说“继续上次督办流程”→读取native-context。未结束时native-start/full恢复原run_id，不清空台账。
- native-next-send在交给邮箱前已持久化关联标记。重复调用先返回lookup_or_continue_original，要求核实原调用而不重发。
- 需要确认→outcome=awaiting_confirmation；用户按cmcc-mail原流程确认后记录最终实际回复。
- 结果未知→outcome=unknown；只查询原调用，不能盲目重发。明确未接受才能记not_sent并允许最多三次尝试。
- 同一回执重放不增加计数。同一邮件不重复应用。业务变化使旧研判/复盘和待发报告失效。
- recover仍是显式恢复上一有效Excel的管理员入口，恢复后先核对发送记录，避免回退后重发。报告发布日志会恢复一致版本。

## 自动任务

在MobileWork配置任务，让当前Agent按prompts/自动任务调用提示词.md执行。没有独立定时器。无人值守是否可发送仍由cmcc-mail/平台正式授权决定；如果它要求逐次确认，就保留待授权状态，不绕过。

## 测试与验收

```bash
python -m unittest discover -s tests -v
python tools/run_native_acceptance.py --output ./native-acceptance-run
```

验收目录必须为空且与生产空间隔离。脚本使用--simulation标记固定AI结果和模拟cmcc-mail语言回复，真实执行CLI/Excel/Word；它不会联网调用真实大模型或邮箱。不要拿该脚本证明平台或邮箱实测成功。模拟研判和复盘不能直接被正式原生流程复用。

真实验收：在MobileWork实际执行一次新增/更新、多任务邮件、拖延原因分析、图表报告和两附件发送，查看真实台账、cmcc-mail实际回复及目标收件箱，再记录通过。当前聊天不能替代该运行环境。
