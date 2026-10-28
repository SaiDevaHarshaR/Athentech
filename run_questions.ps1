$app = "D:\Websites\P441-SahasraAiAgent\SahasraAiAgent"
Set-Location $app
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python -X utf8 questions_test.py --api https://api.athentech.in --client CM --phone 9876543210 --org COMP0108 2>&1 | Tee-Object -FilePath "$app\questions_run.txt"
Write-Host "`nDONE. Attach questions_run.txt and questions_result.csv"
