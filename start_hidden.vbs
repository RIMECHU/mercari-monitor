Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

pythonExe = "C:\Users\17663\AppData\Local\Programs\Python\Python312\python.exe"
If Not objFSO.FileExists(pythonExe) Then pythonExe = "python"

objShell.Run """" & pythonExe & """ """ & scriptDir & "\tray_app.py""", 0, False
