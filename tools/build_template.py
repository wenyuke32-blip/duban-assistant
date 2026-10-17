"""重新生成发布用空模板，不操作任何生产工作空间。"""
import shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from duban.store import Store
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    s=Store(tmp)
    with s.transaction(): pass
    shutil.copy2(s.path,root/'templates'/'督办管理总台账.xlsx')
print('已生成templates/督办管理总台账.xlsx（零业务任务、零邮箱配置）')
