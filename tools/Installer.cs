using Microsoft.Win32;
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Windows.Forms;

[assembly: AssemblyTitle("Kindle EPUB Fixer Setup")]
[assembly: AssemblyDescription("Installer for Kindle EPUB Fixer.")]
[assembly: AssemblyProduct("Kindle EPUB Fixer")]
[assembly: AssemblyCompany("Kindle EPUB Fixer")]
[assembly: AssemblyCopyright("Copyright © 2026 Kindle EPUB Fixer contributors")]
[assembly: AssemblyVersion("1.4.0.2")]
[assembly: AssemblyFileVersion("1.4.0.2")]
[assembly: AssemblyInformationalVersion("1.4.0-beta.2")]

internal static class InstallerProgram
{
    private const string AppName = "Kindle EPUB Fixer";
    private const string AppExeName = "KindleEpubFixer.WinUI.exe";
    private const string ResourceName = "KindleEpubFixer.Payload.zip";
    private const string UninstallRegistryKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\KindleEpubFixer";
    private const string Version = "1.4.0-beta.2";

    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        if (args.Length > 0 && string.Equals(args[0], "/uninstall", StringComparison.OrdinalIgnoreCase))
        {
            return RunUninstall(args);
        }

        if (HasArg(args, "/install") || HasArg(args, "/quiet") || GetArgValue(args, "/dir") != null)
        {
            try
            {
                var installDirectory = GetArgValue(args, "/dir") ?? DefaultInstallDirectory;
                Install(installDirectory, HasArg(args, "/desktop-shortcut"), !HasArg(args, "/no-start-menu"));
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        Application.Run(new InstallForm());
        return 0;
    }

    private static bool HasArg(string[] args, string name)
    {
        return Array.Exists(args, arg => string.Equals(arg, name, StringComparison.OrdinalIgnoreCase));
    }

    private static string GetArgValue(string[] args, string name)
    {
        for (var i = 0; i < args.Length - 1; i++)
        {
            if (string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase))
            {
                return args[i + 1];
            }
        }

        return null;
    }

    private static int RunUninstall(string[] args)
    {
        var quiet = Array.Exists(args, arg => string.Equals(arg, "/quiet", StringComparison.OrdinalIgnoreCase));
        var removeUserData = !Array.Exists(args, arg => string.Equals(arg, "/keep-user-data", StringComparison.OrdinalIgnoreCase));
        var installDirectory = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        if (!IsSafeInstallDirectory(installDirectory))
        {
            MessageBox.Show("Install directory is not safe to remove.", AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        if (!quiet)
        {
            var result = MessageBox.Show(
                "Uninstall Kindle EPUB Fixer and remove installed files, settings, and added fonts?",
                AppName,
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question);
            if (result != DialogResult.Yes)
            {
                return 0;
            }
        }

        try
        {
            KillRunningAppProcesses(installDirectory);
            DeleteShortcuts();
            Registry.CurrentUser.DeleteSubKeyTree(UninstallRegistryKey, throwOnMissingSubKey: false);
            if (removeUserData)
            {
                ScheduleDirectoryRemoval(installDirectory, UserDataDirectory);
            }
            else
            {
                ScheduleDirectoryRemoval(installDirectory);
            }
            if (!quiet)
            {
                MessageBox.Show("Uninstall completed.", AppName, MessageBoxButtons.OK, MessageBoxIcon.Information);
            }

            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static void Install(string installDirectory, bool createDesktopShortcut, bool createStartMenuShortcut)
    {
        installDirectory = Path.GetFullPath(Environment.ExpandEnvironmentVariables(installDirectory));
        if (!IsSafeInstallDirectory(installDirectory))
        {
            throw new InvalidOperationException("Please choose a normal application folder, not a drive root or system folder.");
        }

        Directory.CreateDirectory(installDirectory);
        KillRunningAppProcesses(installDirectory);
        ClearDirectory(installDirectory);

        var payloadZip = WritePayloadToTempZip();
        try
        {
            ZipFile.ExtractToDirectory(payloadZip, installDirectory);
        }
        finally
        {
            TryDeleteFile(payloadZip);
        }

        var currentExe = Assembly.GetExecutingAssembly().Location;
        File.Copy(currentExe, Path.Combine(installDirectory, "Uninstall.exe"), overwrite: true);

        var installedExe = Path.Combine(installDirectory, AppExeName);
        if (!File.Exists(installedExe))
        {
            throw new FileNotFoundException("Installed WinUI executable is missing.", installedExe);
        }

        if (createStartMenuShortcut)
        {
            CreateShortcut(StartMenuShortcutPath, installedExe, installDirectory);
        }
        else
        {
            TryDeleteFile(StartMenuShortcutPath);
        }

        if (createDesktopShortcut)
        {
            CreateShortcut(DesktopShortcutPath, installedExe, installDirectory);
        }
        else
        {
            TryDeleteFile(DesktopShortcutPath);
        }

        WriteUninstallRegistry(installDirectory, installedExe);
    }

    private static string WritePayloadToTempZip()
    {
        var tempZip = Path.Combine(Path.GetTempPath(), "KindleEpubFixer.Install." + Guid.NewGuid().ToString("N") + ".zip");
        using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream(ResourceName))
        {
            if (resource == null)
            {
                throw new InvalidOperationException("Embedded installer payload is missing.");
            }

            using (var output = new FileStream(tempZip, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                resource.CopyTo(output);
            }
        }

        return tempZip;
    }

    private static void ClearDirectory(string directory)
    {
        foreach (var file in Directory.GetFiles(directory))
        {
            File.SetAttributes(file, FileAttributes.Normal);
            File.Delete(file);
        }

        foreach (var child in Directory.GetDirectories(directory))
        {
            Directory.Delete(child, recursive: true);
        }
    }

    private static void KillRunningAppProcesses(string installDirectory)
    {
        var fullInstallDirectory = Path.GetFullPath(installDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        foreach (var process in Process.GetProcesses())
        {
            string path;
            try
            {
                path = process.MainModule.FileName;
            }
            catch
            {
                continue;
            }

            if (!path.StartsWith(fullInstallDirectory, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (process.Id == Process.GetCurrentProcess().Id)
            {
                continue;
            }

            try
            {
                process.Kill();
                process.WaitForExit(5000);
            }
            catch
            {
                // If a process cannot be killed, file replacement will report the real failure.
            }
        }
    }

    private static void WriteUninstallRegistry(string installDirectory, string installedExe)
    {
        using (var key = Registry.CurrentUser.CreateSubKey(UninstallRegistryKey))
        {
            if (key == null)
            {
                return;
            }

            var uninstallExe = Path.Combine(installDirectory, "Uninstall.exe");
            key.SetValue("DisplayName", AppName);
            key.SetValue("DisplayVersion", Version);
            key.SetValue("Publisher", "Kindle EPUB Fixer");
            key.SetValue("InstallLocation", installDirectory);
            key.SetValue("DisplayIcon", installedExe);
            key.SetValue("UninstallString", Quote(uninstallExe) + " /uninstall");
            key.SetValue("QuietUninstallString", Quote(uninstallExe) + " /uninstall /quiet");
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            key.SetValue("EstimatedSize", EstimateDirectorySizeKb(installDirectory), RegistryValueKind.DWord);
        }
    }

    private static int EstimateDirectorySizeKb(string directory)
    {
        long total = 0;
        foreach (var file in Directory.GetFiles(directory, "*", SearchOption.AllDirectories))
        {
            try
            {
                total += new FileInfo(file).Length;
            }
            catch
            {
                // Ignore files that disappear during estimation.
            }
        }

        return (int)Math.Min(int.MaxValue, Math.Max(1, total / 1024));
    }

    private static void CreateShortcut(string shortcutPath, string targetPath, string workingDirectory)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(shortcutPath));

        var shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null)
        {
            return;
        }

        var shell = Activator.CreateInstance(shellType);
        var shortcut = shellType.InvokeMember("CreateShortcut", System.Reflection.BindingFlags.InvokeMethod, null, shell, new object[] { shortcutPath });
        var shortcutType = shortcut.GetType();
        shortcutType.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { targetPath });
        shortcutType.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { workingDirectory });
        shortcutType.InvokeMember("IconLocation", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[] { targetPath });
        shortcutType.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, shortcut, null);
    }

    private static void DeleteShortcuts()
    {
        TryDeleteFile(StartMenuShortcutPath);
        TryDeleteFile(DesktopShortcutPath);
    }

    private static void ScheduleDirectoryRemoval(params string[] directories)
    {
        var tempBatch = Path.Combine(Path.GetTempPath(), "KindleEpubFixer.Uninstall." + Guid.NewGuid().ToString("N") + ".cmd");
        var removalLines = "";
        foreach (var directory in directories)
        {
            if (string.IsNullOrWhiteSpace(directory) || !IsSafeInstallDirectory(directory))
            {
                continue;
            }

            removalLines += "rmdir /s /q " + Quote(Path.GetFullPath(directory)) + "\r\n";
        }

        File.WriteAllText(
            tempBatch,
            "@echo off\r\n" +
            "ping 127.0.0.1 -n 3 > nul\r\n" +
            "for /l %%i in (1,1,20) do (\r\n" +
            removalLines +
            "  ping 127.0.0.1 -n 2 > nul\r\n" +
            ")\r\n" +
            "del /f /q \"%~f0\"\r\n");

        Process.Start(new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = "/c " + Quote(tempBatch),
            CreateNoWindow = true,
            UseShellExecute = false,
            WindowStyle = ProcessWindowStyle.Hidden,
        });
    }

    private static bool IsSafeInstallDirectory(string directory)
    {
        if (string.IsNullOrWhiteSpace(directory))
        {
            return false;
        }

        var full = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var root = Path.GetPathRoot(full).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (string.Equals(full, root, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        var windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var programFilesX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        foreach (var forbidden in new[] { windows, programFiles, programFilesX86, userProfile })
        {
            if (!string.IsNullOrWhiteSpace(forbidden) && string.Equals(full, forbidden, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
        }

        return true;
    }

    private static void TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
            // Best effort cleanup.
        }
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static string StartMenuShortcutPath
    {
        get
        {
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
                "Programs",
                AppName + ".lnk");
        }
    }

    private static string DesktopShortcutPath
    {
        get
        {
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                AppName + ".lnk");
        }
    }

    private static string UserDataDirectory
    {
        get
        {
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "KindleEpubFixer");
        }
    }

    private static string DefaultInstallDirectory
    {
        get
        {
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs",
                "Kindle EPUB Fixer");
        }
    }

    private sealed class InstallForm : Form
    {
        private readonly TextBox _installPathBox;
        private readonly CheckBox _desktopShortcutBox;
        private readonly CheckBox _startMenuShortcutBox;
        private readonly Button _installButton;
        private readonly Button _cancelButton;
        private readonly ProgressBar _progressBar;

        public InstallForm()
        {
            Text = AppName + " Setup";
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            AutoScaleDimensions = new SizeF(96F, 96F);
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(620, 330);
            Font = new Font("Segoe UI", 10F);

            var title = new Label
            {
                Text = "Install " + AppName,
                Font = new Font("Segoe UI", 18F, FontStyle.Bold),
                AutoSize = true,
                Location = new Point(24, 22),
            };
            Controls.Add(title);

            var description = new Label
            {
                Text = "Choose an installation folder. Existing files from an older version will be replaced.",
                AutoSize = false,
                Location = new Point(26, 70),
                Size = new Size(560, 42),
            };
            Controls.Add(description);

            var pathLabel = new Label
            {
                Text = "Install folder",
                AutoSize = true,
                Location = new Point(26, 124),
            };
            Controls.Add(pathLabel);

            _installPathBox = new TextBox
            {
                Text = InstallerProgram.DefaultInstallDirectory,
                Location = new Point(28, 150),
                Size = new Size(470, 30),
            };
            Controls.Add(_installPathBox);

            var browseButton = new Button
            {
                Text = "Browse...",
                Location = new Point(508, 148),
                Size = new Size(86, 34),
            };
            browseButton.Click += (_, __) => BrowseForFolder();
            Controls.Add(browseButton);

            _startMenuShortcutBox = new CheckBox
            {
                Text = "Create Start menu shortcut",
                Checked = true,
                AutoSize = true,
                Location = new Point(30, 202),
            };
            Controls.Add(_startMenuShortcutBox);

            _desktopShortcutBox = new CheckBox
            {
                Text = "Create desktop shortcut",
                Checked = false,
                AutoSize = true,
                Location = new Point(30, 232),
            };
            Controls.Add(_desktopShortcutBox);

            _progressBar = new ProgressBar
            {
                Style = ProgressBarStyle.Marquee,
                MarqueeAnimationSpeed = 0,
                Location = new Point(28, 272),
                Size = new Size(360, 18),
            };
            Controls.Add(_progressBar);

            _installButton = new Button
            {
                Text = "Install",
                Location = new Point(406, 258),
                Size = new Size(90, 38),
            };
            _installButton.Click += (_, __) => BeginInstall();
            Controls.Add(_installButton);

            _cancelButton = new Button
            {
                Text = "Cancel",
                Location = new Point(506, 258),
                Size = new Size(90, 38),
            };
            _cancelButton.Click += (_, __) => Close();
            Controls.Add(_cancelButton);
        }

        private void BrowseForFolder()
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "Choose install folder";
                dialog.SelectedPath = _installPathBox.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    _installPathBox.Text = dialog.SelectedPath;
                }
            }
        }

        private void BeginInstall()
        {
            var installDirectory = _installPathBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(installDirectory))
            {
                MessageBox.Show(this, "Please choose an install folder.", AppName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            _installButton.Enabled = false;
            _cancelButton.Enabled = false;
            _progressBar.MarqueeAnimationSpeed = 30;

            System.Threading.ThreadPool.QueueUserWorkItem(_ =>
            {
                try
                {
                    Install(installDirectory, _desktopShortcutBox.Checked, _startMenuShortcutBox.Checked);
                    BeginInvoke(new Action(() =>
                    {
                        _progressBar.MarqueeAnimationSpeed = 0;
                        MessageBox.Show(this, "Installation completed.", AppName, MessageBoxButtons.OK, MessageBoxIcon.Information);
                        Close();
                    }));
                }
                catch (Exception ex)
                {
                    BeginInvoke(new Action(() =>
                    {
                        _progressBar.MarqueeAnimationSpeed = 0;
                        _installButton.Enabled = true;
                        _cancelButton.Enabled = true;
                        MessageBox.Show(this, ex.Message, AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }));
                }
            });
        }
    }
}
