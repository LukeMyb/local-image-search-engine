Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

BaseDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = BaseDir

WshShell.Run """" & BaseDir & "\.venv\Scripts\pythonw.exe"" """ & BaseDir & "\tray_app.py""", 0, False
