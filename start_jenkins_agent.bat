@echo off
REM Jenkins Windows agent starter — запускать после перезагрузки
REM Node: windows-hevc | Label: windows-hevc
REM Connects via WebSocket + Cloudflare Access headers

java -jar "%~dp0agent.jar" ^
  -url "https://jenkins.multiagent.vision" ^
  -secret "5515c6c30c54c57bbd1e457bec14d78670f02526077b272a4431f897aead7aa1" ^
  -name "windows-hevc" ^
  -webSocket ^
  -webSocketHeader "CF-Access-Client-Id=31ac6b5b8358a3b78703ba425a5eab14.access" ^
  -webSocketHeader "CF-Access-Client-Secret=f739f3dc336681b46781f668c6d127462450d11d06c9a486828638909b59d5ed" ^
  -workDir "%~dp0"
