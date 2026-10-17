"""只检测能力，不安装、不认证、不发邮件。"""
import importlib.util, json, os, platform, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
results={'python':sys.version.split()[0],'platform':platform.system(),'python_supported':sys.version_info>=(3,10),'modules':{m:bool(importlib.util.find_spec(m)) for m in ['openpyxl','docx','matplotlib','pypdf','fcntl']}}
with tempfile.TemporaryDirectory() as tmp:
    a=Path(tmp)/'a'; b=Path(tmp)/'b'; link=Path(tmp)/'link'; a.write_text('probe',encoding='utf-8')
    try:
        os.replace(a,b); link.symlink_to(b); results['atomic_replace_symlink']=link.read_text()=='probe'
    except OSError: results['atomic_replace_symlink']=False
try:
    from duban.reports import chart_font
    results['chinese_chart_font']=bool(chart_font())
except Exception: results['chinese_chart_font']=False
results['not_verified']=['MobileWork重启后持久化','cmcc-mail真实接口/认证/发送授权','真实邮箱收发','宿主AI调用']
print(json.dumps(results,ensure_ascii=False,indent=2))
