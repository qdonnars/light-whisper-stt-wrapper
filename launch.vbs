' Launch Whisper STT with no console window.
'
' Deliberately NOT the .venv interpreter: uv builds its venv launcher unsigned,
' and WDAC refuses to load it ("Une strategie de controle d'application a bloque
' ce fichier", 0x800711C7). The Python Software Foundation build is signed and
' passes the policy, so the app runs against it and its site-packages.
' Install the dependencies there with:  py -3.11 -m pip install -r requirements.txt

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

Set WshShell = CreateObject("WScript.Shell")
userProfile = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")

' Preferred signed interpreters, best first.
candidates = Array( _
  userProfile & "\Programs\Python\Python311\pythonw.exe", _
  userProfile & "\Programs\Python\Python312\pythonw.exe", _
  userProfile & "\Programs\Python\Python313\pythonw.exe" _
)

pythonExe = ""
For Each c In candidates
  If pythonExe = "" And fso.FileExists(c) Then pythonExe = c
Next

If pythonExe = "" Then
  MsgBox "Aucun interpreteur Python signe trouve." & vbCrLf & vbCrLf & _
         "Installez Python depuis python.org, puis :" & vbCrLf & _
         "  py -3.11 -m pip install -r requirements.txt", _
         vbExclamation, "Whisper STT"
  WScript.Quit 1
End If

WshShell.Run """" & pythonExe & """ """ & scriptDir & "\whisper_stt.py""", 0, False
