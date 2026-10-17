# 使用MobileWork自身大模型撰写复盘

直接分析native-report-context返回的statistics、tasks、assisting_tasks及当前有效analyses，不调用另一模型服务。只用本范围资料，证据不足就说明，不伪造趋势/进度/原因。协办可展示但不重复计主责数量。AI推测明确写为可能、待核实。

输出给native-report-text的JSON：
{"run_id":"原流程ID","scope":"政企部","expected_fingerprint":"上下文原值","sections":[{"heading":"风险分析","text":"根据最新反馈，专线交付仍受两处资源不足制约，可能影响排期，需网络部核实资源到位时间后再确认交付安排。","task_ids":["真实任务ID"],"evidence":[{"task_id":"同一真实任务ID","quote":"两处资源不足"}]}]}

heading为总体情况/主要进展/风险分析/协调事项/整改建议/下阶段重点。按资料实际情况形成简洁、正式、可执行的段落；避免重复任务清单和套话。每段列出有关任务ID和可逐字核对的原文。空部门可说明暂无任务，task_ids/evidence为空。所有数字直接取程序statistics，不能自由计算。自动统计正文和图表由程序生成，你的文字会实际嵌入Word，不只是保存在提示词中。
