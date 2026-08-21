@echo off
REM Write folder path to file with UTF-8 encoding
chcp 65001 >nul
echo %~1> %2
