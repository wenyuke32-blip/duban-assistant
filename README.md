# 督办盯梢小助手 V1.1 审计修复版

[下载完整V1.1 ZIP](https://github.com/wenyuke32-blip/duban-assistant/raw/refs/heads/main/downloads/duban-assistant-v1.1.zip) · [四类端到端验收报告](docs/端到端验收报告.md) · [部署操作说明](docs/部署操作说明_V1.1.md)

当前不能认定项目已完成MobileWork生产上线。已经实际运行的是本地确定性业务内核；真实模型、cmcc-mail绑定模块尚未实现，企业邮箱搜索/附件下载/发送和无人值守授权未验证。不得把提示词、fixture或函数存在当作真实能力通过。

本版重点修复重复更新/报告入队、空证据和非法字段、旧AI研判失效、附件来源验证与分页恢复，以及报告发布和台账提交窗口的中断恢复。详细证据见验收报告及docs/evidence。

```bash
python tools/check_environment.py
python -m duban init --workspace ./workspace-data
python -m duban doctor --workspace ./workspace-data
python -m duban add --workspace ./workspace-data --file examples/新增任务.json
python -m duban reports --workspace ./workspace-data
python -m unittest discover -s tests -v
python tools/run_acceptance.py --output ./acceptance-run
```

运行条件：Python3.10+、Linux/POSIX、中文字体、requirements.txt中的依赖。能力探测仅验证当前环境；不能假设MobileWork允许Python或安装依赖。acceptance-run必须为空且与生产目录分离。最后一条用合成任务真实写本地文件，并用明确标记的模拟宿主验证调用链，真实邮件和真实模型调用次数均为0。

发布包含SKILL.md、代码、空白台账、提示词/schema、测试、两条端到端流程、测试证据及中文部署说明。生产初始化不导入样例。tests/fixture_adapter.py只能用于验收，不能用于生产。
