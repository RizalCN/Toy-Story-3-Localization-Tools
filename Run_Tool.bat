@echo off
cd /d "%~dp0"
py -3 Toy_Story3_DCT_Safe_Translator.py
if errorlevel 1 pause
