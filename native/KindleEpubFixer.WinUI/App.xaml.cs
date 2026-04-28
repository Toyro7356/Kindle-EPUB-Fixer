using Microsoft.UI.Xaml;

namespace KindleEpubFixer.WinUI;

public partial class App : Application
{
    public static MainWindow? MainWindowInstance { get; private set; }

    public App()
    {
        InitializeComponent();
        UnhandledException += (_, args) =>
        {
            try
            {
                var path = Path.Combine(AppContext.BaseDirectory, "winui-crash.log");
                File.AppendAllText(path, $"{DateTimeOffset.Now:u} {args.Exception}\n");
            }
            catch
            {
                // Last-chance logging must never throw.
            }
        };
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        MainWindowInstance = new MainWindow();
        MainWindowInstance.Activate();
    }
}
