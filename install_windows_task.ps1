$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = "ActiveETF 00981A MoneyDJ Daily Holdings"
$runAt = "18:30"
$batPath = Join-Path $projectDir "run_00981a_daily.bat"

New-Item -ItemType Directory -Force -Path (Join-Path $projectDir "logs") | Out-Null

$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $projectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $runAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Fetch MoneyDJ 00981A holdings daily and compare with the previous snapshot." `
    -Force

Write-Host "Registered scheduled task: $taskName"
Write-Host "Daily run time: $runAt"
