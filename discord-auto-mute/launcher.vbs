Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir

' 1. 디스코드 앱 실행 (Canary 우선 탐색)
canaryUpdate = localAppData & "\DiscordCanary\Update.exe"
normalUpdate = localAppData & "\Discord\Update.exe"

If fso.FileExists(canaryUpdate) Then
    WshShell.Run """" & canaryUpdate & """ --processStart DiscordCanary.exe", 1, False
ElseIf fso.FileExists(normalUpdate) Then
    WshShell.Run """" & normalUpdate & """ --processStart Discord.exe", 1, False
End If

' 2. discord_mute 실행 (EXE 우선, 없으면 pythonw 또는 실행하기.bat)
exePath = currentDir & "\dist\discord_mute.exe"
pyPath = currentDir & "\discord_mute.py"
batPath = currentDir & "\실행하기.bat"

If fso.FileExists(exePath) Then
    WshShell.Run """" & exePath & """", 0, False
ElseIf fso.FileExists(pyPath) Then
    WshShell.Run "pythonw.exe """ & pyPath & """", 0, False
Else
    WshShell.Run """" & batPath & """", 0, False
End If
