# Backward-compatible launcher for the non-Streamlit web dashboard.
& (Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "scripts\run_web_workstation.ps1") @args
