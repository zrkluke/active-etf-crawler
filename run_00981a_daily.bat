@echo off
setlocal

cd /d "%~dp0"
if not exist logs mkdir logs
python moneydj_00981a_holdings.py >> logs\00981a_daily.log 2>&1
