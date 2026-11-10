Set WshShell = CreateObject("WScript.Shell")
' 0은 창 숨김 모드, False는 기다리지 않고 바로 실행하라는 뜻입니다.
WshShell.Run chr(34) & "C:\KaMuEumGok\KaMuEumGok.bat" & chr(34), 0, False
Set WshShell = Nothing