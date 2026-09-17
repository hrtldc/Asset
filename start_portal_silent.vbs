Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "G:\JSUDS\Asset"
' Launch server completely in the background (0 = hidden window)
WshShell.Run "cmd /c ""C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"" start_service.py", 0, False
' Wait 1.5 seconds for server to bind port 8088
WScript.Sleep 1500
' Open default browser to the local portal
WshShell.Run "http://127.0.0.1:8088/"
