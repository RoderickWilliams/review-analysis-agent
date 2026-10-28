param(
  [string]$InstallDir = (Split-Path -Parent $PSScriptRoot),
  [switch]$WithDev,
  [switch]$WithScrapling,
  [switch]$Minimal,
  [switch]$SkipTests,
  [switch]$RunChecks
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path $InstallDir).Path
Write-Host "[1/5] 仓库: $repo"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw '未找到 python，请先安装 Python 3.10+ 并加入 PATH' }
$version = & python -c "import sys;print('%d.%d' % sys.version_info[:2])"
if ([version]::Parse($version) -lt [version]::Parse('3.10')) { throw "Python $version 低于 3.10" }
Write-Host "[2/5] Python $version"

$venv = Join-Path $repo '.venv'
if (-not (Test-Path $venv)) { & python -m venv $venv }
$py = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) { throw "虚拟环境创建失败: $py" }
& $py -m pip install --upgrade pip --disable-pip-version-check | Out-Null
Write-Host "[3/5] 安装 review-agent"

Push-Location $repo
try {
  $extras = if ($Minimal) { 'api' } else { 'api,import' }
  if ($WithDev) { $extras += ',dev' }
  if ($WithScrapling) { $extras += ',scrapling' }
  & $py -m pip install -e ".[$extras]" --disable-pip-version-check
  if ($LASTEXITCODE -ne 0) { throw "pip install 失败，退出码 $LASTEXITCODE" }

  $envFile = Join-Path $repo '.env'
  if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $repo '.env.example') $envFile
    Write-Host "[4/5] 已生成 .env，请填入 DEEPSEEK_API_KEY 或 REVIEWAGENT_API_KEYS"
  } else {
    Write-Host "[4/5] .env 已存在，跳过"
  }

  if ($RunChecks) {
    & $py -m reviewagent doctor
    if ($LASTEXITCODE -ne 0) { Write-Warning "doctor 退出码 $LASTEXITCODE" }
  }

  if ($RunChecks -and $WithDev -and -not $SkipTests) {
    Write-Host "[5/5] 运行测试"
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "测试失败，退出码 $LASTEXITCODE" }
  } else {
    Write-Host "[5/5] 跳过检查（单独获准后加 -RunChecks；测试另需 -WithDev）"
  }
  Write-Host "完成: $py -m reviewagent --help"
}
finally { Pop-Location }
