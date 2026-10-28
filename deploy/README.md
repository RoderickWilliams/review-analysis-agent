# 本地运行与打包

本次修改尚未运行构建或部署验收。以下为实施后的使用入口。

## Windows

在 cmd 中从仓库根执行：

~~~cmd
deploy\setup.cmd
start.bat
~~~

安装只建立项目 .venv 并安装 api、import 扩展，不安装系统 Python、浏览器或全量采集依赖，也不运行检查。已有环境可直接运行：

~~~cmd
.venv\Scripts\python.exe -m reviewagent serve --host 127.0.0.1 --port 8000
~~~

工作台 http://127.0.0.1:8000/app/，接口文档 /docs。模型配置前可以创建和导入，实际分析需配置模型。旧 setup.ps1 保留兼容；检查仅在显式传入 -RunChecks 后执行，安装开发依赖不等于同意检查。

## Docker

运行前在本地 .env 或 Compose 环境中设置模型配置和 REVIEWAGENT_ACCESS_TOKEN。令牌由你管理，不随镜像分发。容器监听 0.0.0.0，因此必须设置令牌；宿主机端口仍仅绑定回环地址。

~~~sh
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
~~~

界面访问令牌在右上角设置中填写，仅保留在页面内存。镜像包含 API、文件导入与非图形 OCR 组件；不包含浏览器登录状态。现有 data 和 output 仍作为运行卷挂载，首次在新环境部署可另行指定新目录。

任务调度器为进程内线程池，使用单 worker。不要启动多个 worker 或多容器共同调度同一数据库。当前没有多用户权限体系或分布式任务恢复。

## 桌面发行包

需要在独立构建环境自行安装 PyInstaller 和项目所需扩展。只在打包获准后运行：

~~~cmd
python -m pip install ".[api,import]" pyinstaller
python -m PyInstaller review_agent.spec
~~~

spec 以自身目录定位工程，收集明确的静态文件和依赖，不复制用户 .env、Cookie、浏览器 profile、运行数据库或输出。dist/ReviewAgent 是安装器的输入。Inno Setup 脚本以当前项目为基准，无旧机器绝对路径。

桌面启动只监听 127.0.0.1:8000，数据根默认用户 LocalAppData/ReviewAgent，不写安装目录，不自动迁移旧数据。

## 验证与恢复

本轮没有运行以下命令。按工作约定，检查需先取得对应范围的一次批准。

~~~cmd
python -m pytest -m "not live"
node --check src/reviewagent/webui/workbench.js
python -m pip wheel --no-deps --no-build-isolation . --wheel-dir .validation-dist
python tools/check_dist.py .validation-dist
~~~

离线测试使用临时数据目录与假模型，并阻止外部网络连接。wheel 检查仅检查资源和禁止文件名，不等同于完整供应链扫描。手动 CI 没有 push / PR 自动触发，也不上传制品。

备份或迁移数据须自行先停止写入并复制完整数据目录。旧 JSON 历史迁移默认关闭；设置 REVIEWAGENT_MIGRATE_LEGACY_HISTORY=1 才会执行已有兼容迁移逻辑。迁移后旧 JSON 会改名为 .json.migrated，应先备份。
