@echo off
rem Memasang semua yang dibutuhkan Laporan Ampyang di Windows.
rem Cukup klik dua kali file ini. Aman dijalankan berulang kali.
setlocal
cd /d "%~dp0\.."

where py >nul 2>nul
if errorlevel 1 (
    echo Python belum terpasang. Memasang Python 3.12 lewat winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo.
        echo Gagal memasang Python otomatis. Unduh manual dari https://www.python.org/downloads/
        echo dan CENTANG "Add python.exe to PATH" saat memasang.
        pause
        exit /b 1
    )
    echo.
    echo Python sudah terpasang. TUTUP jendela ini lalu klik dua kali pasang.bat sekali lagi.
    pause
    exit /b 0
)

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo Versi Python terlalu lama. Dibutuhkan 3.11 atau lebih baru.
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo Tutup jendela ini lalu jalankan pasang.bat sekali lagi.
    pause
    exit /b 1
)

if not exist .venv (
    echo Membuat lingkungan Python khusus aplikasi ini...
    py -3 -m venv .venv || goto gagal
)
echo Memasang paket yang dibutuhkan (butuh internet, sekali saja)...
.venv\Scripts\python -m pip install --upgrade pip >nul
.venv\Scripts\python -m pip install -r requirements.txt || goto gagal

if not exist .env copy .env.example .env >nul

echo.
echo Selesai. Jalankan aplikasi dengan klik dua kali scripts\jalankan.bat
pause
exit /b 0

:gagal
echo.
echo Pemasangan gagal. Salin pesan di atas dan kirimkan ke pengelola aplikasi.
pause
exit /b 1
