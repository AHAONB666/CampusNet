' CampusNet launcher
' Double-click to start CampusNet.exe.
' The first-run guide is now built into the app, so no extra script is needed.
' Safe to copy to the Desktop or Start Menu as long as it stays one level
' below (or next to) CampusNet.exe.

Option Explicit

Dim fso, sh, dir, exe

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
exe = dir & "\CampusNet.exe"

If Not fso.FileExists(exe) Then
    exe = dir & "\..\CampusNet.exe"
End If

If Not fso.FileExists(exe) Then
    MsgBox "CampusNet.exe was not found." & vbCrLf & vbCrLf & _
           "Keep this launcher in the CampusNet\launcher folder" & vbCrLf & _
           "(or one level below CampusNet.exe).", 16, "CampusNet"
    WScript.Quit 1
End If

sh.CurrentDirectory = fso.GetParentFolderName(exe)
sh.Run """" & exe & """", 1, False
