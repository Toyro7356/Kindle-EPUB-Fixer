using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class PortableLauncher
{
    [STAThread]
    private static int Main()
    {
        var baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        var appDirectory = Path.Combine(baseDirectory, "app");
        var appPath = Path.Combine(appDirectory, "KindleEpubFixer.WinUI.exe");

        if (!File.Exists(appPath))
        {
            MessageBox.Show(
                "找不到 app\\KindleEpubFixer.WinUI.exe。请完整解压便携版后再运行。",
                "Kindle EPUB Fixer",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }

        Process.Start(new ProcessStartInfo
        {
            FileName = appPath,
            WorkingDirectory = appDirectory,
            UseShellExecute = false,
        });
        return 0;
    }
}
