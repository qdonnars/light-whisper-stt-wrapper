Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """" & scriptDir & "\.venv\Scripts\pythonw.exe"" """ & scriptDir & "\whisper_stt.py""", 0, False
