# 督办盯梢小助手 V1.2：MobileWork原生协作版

[下载V1.2完整ZIP](https://github.com/wenyuke32-blip/duban-assistant/raw/refs/heads/main/downloads/duban-assistant-v1.2.zip) · [部署操作](docs/MobileWork原生部署_V1.2.md) · [验收结果](docs/端到端验收报告.md)

**AI直接使用MobileWork自身的大模型，邮箱直接用自然语言调用cmcc-mail。** 不需要额外模型API、邮箱HTTP接口或必须编写的Python适配模块。

MobileWork读SKILL.md，自己理解主管反馈、分析拖延原因和撰写复盘；直接委托cmcc-mail查信/发信。程序保存结果、维护固定Excel、计算统计、去重及生成10份带图表和复盘的Excel/Word文件。JSON及后台命令由宿主内部完成，不要求管理员手写。

默认full返回原生协作阶段，由MobileWork持续执行到完成/待确认；中断后恢复原检查点，未知发送先核实原调用。旧--adapter保留兼容，不是默认前提。

```bash
python tools/check_environment.py
python -m duban init --workspace ./workspace-data
python -m duban full --workspace ./workspace-data
```

管理员在MobileWork直接说“执行完整督办流程”；具体后台步骤见SKILL.md。首次只需确认固定目录、真实联系人和实际业务资料，认证/发送确认由cmcc-mail按其规则处理。

```bash
python -m unittest discover -s tests -v
python tools/run_native_acceptance.py --output ./native-acceptance-run
```

本地验收真实写入文件，但AI内容与邮箱语言回复为显式模拟，真实外部模型/邮件调用均0，不能宣称已经在你的MobileWork完成实测。正式运行仍应在目标平台核实脚本权限、持久化、分析效果和实际邮箱结果。

运行条件：Python3.10+、Linux/POSIX、中文字体及requirements.txt依赖；只在平台允许时配置依赖。工作空间固定文件为督办管理总台账.xlsx。源码包不是平台签名安装包。
