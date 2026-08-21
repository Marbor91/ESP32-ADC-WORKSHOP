@echo off
:: Проверка и запрос прав администратора
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
"%temp%\getadmin.vbs"
del "%temp%\getadmin.vbs"
exit /B

:gotAdmin
pushd "%~dp0"

:: Укажите путь к вашему python.exe и вашему .py файлу (в кавычках, если есть пробелы)
python "C:\Users\Marbor\YandexDisk\OTUS\ОУ АЦП ESP32. Оцифровать сигнал\ESP32-ADC-WORKSHOP\plotter.py"

pause