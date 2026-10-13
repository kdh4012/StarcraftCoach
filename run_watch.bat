@echo off
REM 빅헌터 코치 감시 모드 실행 (게임 끝나면 리포트 자동 오픈)
chcp 65001 > nul
cd /d %~dp0
python -m bhcoach watch
pause
