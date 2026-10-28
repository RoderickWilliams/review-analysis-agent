# -*- mode: python ; coding: utf-8 -*-
"""Desktop API workbench. Build resources use an explicit public-file whitelist."""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve()
datas = [(str(ROOT / "LICENSE"), ".")]
for variant in ("webui", "webui-classic", "webui-redesign"):
    folder = ROOT / "src" / "reviewagent" / variant
    for pattern in ("*.html", "*.css", "*.js", "*.png"):
        datas.extend((str(item), "reviewagent/" + variant) for item in folder.glob(pattern))
datas += collect_data_files("jieba")
hiddenimports = collect_submodules("uvicorn") + collect_submodules("sklearn")
hiddenimports += ["reviewagent.http_api", "reviewagent.analysis_tasks", "reviewagent.collection", "reviewagent.insights", "reviewagent.scrapers.xhs_reader", "openpyxl", "multipart"]
a = Analysis([str(ROOT / "desktop_launcher.py")], pathex=[str(ROOT / "src")], datas=datas, hiddenimports=hiddenimports, excludes=["pytest", "notebook", "IPython", "streamlit"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ReviewAgent", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ReviewAgent", upx=False)
