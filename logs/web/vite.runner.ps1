$ErrorActionPreference = "Continue"
Set-Location "E:\学习文件\研究生\就业\Agent学习\Evidence-first Travel Intelligence Agent\apps\web"
$env:VITE_DIRECT_AGENT = "true"
$env:VITE_AGENT_BASE_URL = "http://127.0.0.1:8001"
& "D:\Software\Nodejs\npm.cmd" run dev -- --host "127.0.0.1" --port "5173" --strictPort
