Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir

' 1. 디스코드 앱 실행 (Discord Canary 우선 탐색, 없으면 일반 Discord 실행)
canaryUpdate = localAppData & "\DiscordCanary\Update.exe"
normalUpdate = localAppData & "\Discord\Update.exe"

If fso.FileExists(canaryUpdate) Then
    WshShell.Run """" & canaryUpdate & """ --processStart DiscordCanary.exe", 1, False
ElseIf fso.FileExists(normalUpdate) Then
    WshShell.Run """" & normalUpdate & """ --processStart Discord.exe", 1, False
End If

' 2. discord_mute 실행 (pythonw.exe로 즉각 백그라운드 실행)
exePath = currentDir & "\dist\discord_mute.exe"
pyPath = currentDir & "\discord_mute.py"
pythonwPath = localAppData & "\Programs\Python\Python313\pythonw.exe"

If fso.FileExists(pythonwPath) Then
    WshShell.Run """" & pythonwPath & """ """ & pyPath & """", 0, False
ElseIf fso.FileExists(exePath) Then
    WshShell.Run """" & exePath & """", 0, False
Else
    WshShell.Run "pythonw.exe """ & pyPath & """", 0, False
End If
