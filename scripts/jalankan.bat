@echo off
rem Menjalankan Laporan Ampyang. Browser terbuka otomatis ke http://localhost:8000
rem Tutup jendela ini untuk mematikan aplikasi.
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe (
    echo Aplikasi belum dipasang. Klik dua kali scripts\pasang.bat dulu.
    pause
    exit /b 1
)
echo Laporan Ampyang berjalan di http://localhost:8000
echo Jangan tutup jendela ini selama aplikasi dipakai.
.venv\Scripts\python run.py
pause
