namespace KindleEpubFixer.WinUI.Services;

public static class AppPaths
{
    public static string AppBaseDirectory => AppContext.BaseDirectory;

    public static string UserDataDirectory
    {
        get
        {
            var directory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "KindleEpubFixer");
            Directory.CreateDirectory(directory);
            return directory;
        }
    }

    public static string BundledFontsDirectory => Path.Combine(AppBaseDirectory, "fonts");

    public static string FontsDirectory
    {
        get
        {
            var directory = Path.Combine(UserDataDirectory, "fonts");
            Directory.CreateDirectory(directory);
            return directory;
        }
    }

    public static string UserFontsDirectory
    {
        get
        {
            var directory = Path.Combine(FontsDirectory, "user");
            Directory.CreateDirectory(directory);
            return directory;
        }
    }

    public static string AppSettingsPath => Path.Combine(FontsDirectory, "app-settings.json");

    public static string FontSettingsPath => Path.Combine(FontsDirectory, "font-settings.json");

    public static string FontSearchPath
    {
        get
        {
            var paths = new List<string> { FontsDirectory };
            if (Directory.Exists(BundledFontsDirectory))
            {
                paths.Add(BundledFontsDirectory);
            }

            return string.Join(Path.PathSeparator, paths);
        }
    }

    public static string? BackendExecutable
    {
        get
        {
            var local = Path.Combine(AppBaseDirectory, "KindleEpubFixer.Backend.exe");
            if (File.Exists(local))
            {
                return local;
            }

            var probe = new DirectoryInfo(AppBaseDirectory);
            while (probe is not null)
            {
                var candidate = Path.Combine(probe.FullName, "dist", "KindleEpubFixer.Backend.exe");
                if (File.Exists(candidate))
                {
                    return candidate;
                }

                probe = probe.Parent;
            }

            return null;
        }
    }

    public static string? BackendScript
    {
        get
        {
            var probe = new DirectoryInfo(AppBaseDirectory);
            while (probe is not null)
            {
                var candidate = Path.Combine(probe.FullName, "main_backend.py");
                if (File.Exists(candidate))
                {
                    return candidate;
                }

                probe = probe.Parent;
            }

            return null;
        }
    }

    public static string PythonExecutable
    {
        get
        {
            var probe = new DirectoryInfo(AppBaseDirectory);
            while (probe is not null)
            {
                var candidate = Path.Combine(probe.FullName, ".venv", "Scripts", "python.exe");
                if (File.Exists(candidate))
                {
                    return candidate;
                }

                probe = probe.Parent;
            }

            return "python";
        }
    }
}
