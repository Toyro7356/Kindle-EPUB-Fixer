using System.Runtime.InteropServices;
using KindleEpubFixer.WinUI.Views;
using Microsoft.UI.Composition.SystemBackdrops;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Graphics;
using WinRT.Interop;

namespace KindleEpubFixer.WinUI;

public sealed partial class MainWindow : Window
{
    private const int MinWindowWidth = 1080;
    private const int MinWindowHeight = 760;
    private const int GwlpWndProc = -4;
    private const int WmGetMinMaxInfo = 0x0024;

    private readonly WndProcDelegate _wndProc;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _notificationTimer;
    private nint _oldWndProc;
    private HomePage? _homePage;
    private SettingsPage? _settingsPage;
    private AboutPage? _aboutPage;

    public MainWindow()
    {
        InitializeComponent();
        ConfigureTitleBar();
        TrySetBackdrop();
        _notificationTimer = DispatcherQueue.CreateTimer();
        _notificationTimer.Interval = TimeSpan.FromSeconds(3);
        _notificationTimer.Tick += (_, _) =>
        {
            _notificationTimer.Stop();
            NotificationBar.IsOpen = false;
        };

        _wndProc = WndProc;
        InstallMinSizeHook();
        SetWindowIcon();
        AppWindow.Resize(new SizeInt32(1180, 760));

        RootNav.SizeChanged += (_, _) => EnforceMinimumWindowSize();
        RootNav.SelectedItem = HomeItem;
        ShowPage("Home");
    }

    public void ShowNotification(string title, string? message = null, InfoBarSeverity severity = InfoBarSeverity.Informational)
    {
        NotificationBar.Title = title;
        NotificationBar.Message = CompactNotificationMessage(message);
        NotificationBar.Severity = severity;
        NotificationBar.IsOpen = true;

        _notificationTimer.Stop();
        _notificationTimer.Start();
    }

    private static string CompactNotificationMessage(string? message)
    {
        if (string.IsNullOrWhiteSpace(message))
        {
            return string.Empty;
        }

        const int maxLength = 42;
        var trimmed = message.Trim();
        return trimmed.Length <= maxLength ? trimmed : trimmed[..maxLength] + "...";
    }

    private void ConfigureTitleBar()
    {
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        var titleBar = AppWindow.TitleBar;
        titleBar.BackgroundColor = Microsoft.UI.Colors.Transparent;
        titleBar.InactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
        titleBar.ButtonBackgroundColor = Microsoft.UI.Colors.Transparent;
        titleBar.ButtonInactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
        titleBar.ButtonHoverBackgroundColor = Windows.UI.Color.FromArgb(32, 0, 0, 0);
        titleBar.ButtonPressedBackgroundColor = Windows.UI.Color.FromArgb(48, 0, 0, 0);
        titleBar.ButtonForegroundColor = Microsoft.UI.Colors.Black;
        titleBar.ButtonInactiveForegroundColor = Microsoft.UI.Colors.Gray;
    }

    private void TrySetBackdrop()
    {
        try
        {
            SystemBackdrop = new MicaBackdrop { Kind = MicaKind.BaseAlt };
        }
        catch
        {
            SystemBackdrop = null;
        }
    }

    private void RootNav_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is NavigationViewItem { Tag: string tag })
        {
            ShowPage(tag);
        }
    }

    private void ShowPage(string tag)
    {
        ContentHost.Children.Clear();
        switch (tag)
        {
            case "Settings":
                _settingsPage ??= CreateSettingsPage();
                ContentHost.Children.Add(_settingsPage);
                break;
            case "About":
                _aboutPage ??= new AboutPage();
                ContentHost.Children.Add(_aboutPage);
                break;
            default:
                _homePage ??= CreateHomePage();
                _homePage.RefreshSettings();
                ContentHost.Children.Add(_homePage);
                break;
        }
    }

    private HomePage CreateHomePage()
    {
        var page = new HomePage();
        page.StatusChanged += (_, status) => StatusText.Text = status;
        return page;
    }

    private SettingsPage CreateSettingsPage()
    {
        var page = new SettingsPage();
        page.SettingsSaved += (_, _) => _homePage?.RefreshSettings();
        return page;
    }

    private void InstallMinSizeHook()
    {
        var hwnd = WindowNative.GetWindowHandle(this);
        _oldWndProc = SetWindowLongPtr(hwnd, GwlpWndProc, Marshal.GetFunctionPointerForDelegate(_wndProc));
    }

    private void SetWindowIcon()
    {
        var iconPath = Path.Combine(AppContext.BaseDirectory, "Assets", "app.ico");
        if (File.Exists(iconPath))
        {
            AppWindow.SetIcon(iconPath);
        }
    }

    private void EnforceMinimumWindowSize()
    {
        var size = AppWindow.Size;
        var width = Math.Max(size.Width, MinWindowWidth);
        var height = Math.Max(size.Height, MinWindowHeight);
        if (width != size.Width || height != size.Height)
        {
            AppWindow.Resize(new SizeInt32(width, height));
        }
    }

    private nint WndProc(nint hwnd, uint msg, nint wParam, nint lParam)
    {
        if (msg == WmGetMinMaxInfo)
        {
            var minMaxInfo = Marshal.PtrToStructure<MinMaxInfo>(lParam);
            minMaxInfo.MinTrackSize.X = MinWindowWidth;
            minMaxInfo.MinTrackSize.Y = MinWindowHeight;
            Marshal.StructureToPtr(minMaxInfo, lParam, true);
        }

        return CallWindowProc(_oldWndProc, hwnd, msg, wParam, lParam);
    }

    private delegate nint WndProcDelegate(nint hwnd, uint msg, nint wParam, nint lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct Point
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MinMaxInfo
    {
        public Point Reserved;
        public Point MaxSize;
        public Point MaxPosition;
        public Point MinTrackSize;
        public Point MaxTrackSize;
    }

    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")]
    private static extern nint SetWindowLongPtr(nint hwnd, int index, nint newProc);

    [DllImport("user32.dll")]
    private static extern nint CallWindowProc(nint previousProc, nint hwnd, uint msg, nint wParam, nint lParam);
}
