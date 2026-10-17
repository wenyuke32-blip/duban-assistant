# 督办盯梢小助手 V1.0

[点击下载完整项目 ZIP（含 Excel 模板）](https://github.com/wenyuke32-blip/duban-assistant/raw/refs/heads/main/downloads/督办盯梢小助手_V1.0.zip)

也可点击仓库页面的 **Code → Download ZIP** 下载全部源码。

根据《督办盯梢小助手_Codex开发提示词_V1.0》制作的MobileWork Skill源码项目。包含可执行Python业务内核、固定Excel台账模板、图表报告、宿主AI/邮箱适配合同、测试与中文指南。

**可本地运行：** 台账初始化/增量管理、Excel导入、归档/重开、去重与异常保护、预警入队、四部门和管理员共10份带图表Excel/Word报告。

**上线阻塞：** 尚未取得cmcc-mail SKILL.md、MobileWork实际工具/执行规则、宿主AI和真实邮箱会话；真实自动收发、无人值守发送授权、宿主持久化尚未验收。邮箱和AI调用链需要企业按真实接口绑定，不能将本包视为已完成企业平台部署。详见docs/邮件与宿主适配.md与docs/验收清单.md。

在本项目根目录：

```bash
python tools/check_environment.py
python -m duban init --workspace ./workspace-data
python -m duban add --workspace ./workspace-data --file examples/新增任务.json
python -m duban query --workspace ./workspace-data
python -m duban reports --workspace ./workspace-data
python -m unittest discover -s tests -v
```

依赖见requirements.txt；需Python3.10+、Linux/POSIX及中文图表字体。平台未允许安装依赖时不要自行安装。首次初始化不会放入演示任务，examples中的example.invalid地址永远不是生产收件人。

入口说明：SKILL.md；部署恢复：docs/部署与恢复.md；日常操作：docs/日常使用指南.md；自动任务：prompts/自动任务调用提示词.md；测试证据：docs/本地测试结果.txt。空模板在templates，不能覆盖已有台账。
