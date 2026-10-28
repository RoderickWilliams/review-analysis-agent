"""Inspect a built wheel without importing ReviewAgent or touching runtime data."""
from pathlib import Path
import sys
import zipfile


def inspect_dist(directory):
    wheels = list(Path(directory).glob('*.whl'))
    if not wheels:
        raise SystemExit('没有 wheel 文件')
    required = {'reviewagent/webui/index.html', 'reviewagent/webui/logo.png', 'reviewagent/webui/workbench.css', 'reviewagent/webui/workbench.js', 'reviewagent/webui/workbench-extra.js', 'reviewagent/webui-classic/index.html', 'reviewagent/webui-redesign/index.html'}
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            if required - names:
                raise SystemExit(f'缺少工作台资源：{sorted(required - names)}')
            forbidden = []
            for name in names:
                parts = {part.lower() for part in Path(name).parts}
                if parts & {'.env', 'cookies', 'browser-profile', 'browser-profiles', 'playwright-data', 'output', '.cache'} or name.lower().endswith(('.db', '.sqlite', '.sqlite3', '.pem', '.key')):
                    forbidden.append(name)
            if forbidden:
                raise SystemExit(f'发行包包含运行数据或敏感文件：{forbidden}')
        print(f'{wheel.name}: 静态资源齐全，未发现禁止打包的文件名')


if __name__ == '__main__':
    inspect_dist(sys.argv[1] if len(sys.argv) > 1 else '.validation-dist')
