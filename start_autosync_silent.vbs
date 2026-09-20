' 3D USD Asset Portal - silent launcher for auto-sync daemon
' Double-click to run watch_and_sync.py in background (no window)
Option Explicit

Dim fso, shell, baseDir
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)

' If lock file exists, daemon is already running
If fso.FileExists(baseDir & "\logs\.autosync.lock") Then
    MsgBox "Auto-sync daemon appears to be already running." & vbCrLf & _
           "To restart, run stop_autosync.bat first.", 64, "USD Asset Portal"
    WScript.Quit
End If

shell.CurrentDirectory = baseDir
' 0 = hidden window, False = do not wait
shell.Run "cmd /c """ & baseDir & "\start_autosync.bat""", 0, False
