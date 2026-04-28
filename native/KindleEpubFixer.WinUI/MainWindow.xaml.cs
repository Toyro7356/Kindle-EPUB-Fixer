using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Runtime.InteropServices;
using Windows.Graphics;
using WinRT.Interop;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Composition.SystemBackdrops;
using KindleEpubFixer.WinUI.Views;

namespace KindleEpubFixer.WinUI;

public sealed partial class MainWindow : Window
{
    private const int MinWindowWidth = 1040;
    private const int MinWindowHeight = 640;
    private const int GwlpWndProc = -4;
    private const int WmGetMinMaxInfo = 0x0024;
    private readonly WndProcDelegate _wndProc;
    private nint _oldWndProc;
    private NavigationView RootNav = null!;
    private NavigationViewItem HomeItem = null!;
    private Grid ContentHost = null!;
    private TextBlock StatusText = null!;
    private HomePage? _homePage;
    private SettingsPage? _settingsPage;
    private AboutPage? _aboutPage;

    public MainWindow()
    {
        InitializeComponent();
        TrySetBackdrop();
        BuildShell();
        _wndProc = WndProc;
        InstallMinSizeHook();
        SetWindowIcon();
        AppWindow.Resize(new SizeInt32(1180, 760));
        RootNav.SizeChanged += (_, _) => EnforceMinimumWindowSize();
        RootNav.Loaded += (_, _) => ApplyNavigationPaneBackground();
        RootNav.PaneOpened += (_, _) => ApplyNavigationPaneBackground();
        RootNav.SelectedItem = HomeItem;
        ShowPage("Home");
    }

    private void BuildShell()
    {
        RootNav = new NavigationView
        {
            AlwaysShowHeader = false,
            IsBackButtonVisible = NavigationViewBackButtonVisible.Collapsed,
            IsSettingsVisible = false,
            IsPaneOpen = false,
            OpenPaneLength = 240,
            CompactPaneLength = 56,
            PaneDisplayMode = NavigationViewPaneDisplayMode.LeftCompact,
            PaneTitle = "Kindle EPUB Fixer",
            Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
        };
        RootNav.SelectionChanged += RootNav_SelectionChanged;

        HomeItem = CreateNavigationItem("主页", Symbol.Home, "Home");
        RootNav.MenuItems.Add(HomeItem);
        RootNav.MenuItems.Add(CreateNavigationItem("设置", Symbol.Setting, "Settings"));
        RootNav.MenuItems.Add(CreateNavigationItem("关于", Symbol.Help, "About"));

        var scrollViewer = new ScrollViewer
        {
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollMode = ScrollMode.Enabled,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            VerticalScrollMode = ScrollMode.Enabled,
        };

        var pageGrid = new Grid
        {
            Padding = new Thickness(24, 18, 24, 22),
            MinWidth = 980,
            MinHeight = 560,
            Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
        };
        pageGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        pageGrid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });

        pageGrid.Children.Add(BuildTitleBar());
        ContentHost = new Grid();
        Grid.SetRow(ContentHost, 1);
        pageGrid.Children.Add(ContentHost);
        scrollViewer.Content = pageGrid;
        RootNav.Content = scrollViewer;
        RootGrid.Children.Add(RootNav);
    }

    private static NavigationViewItem CreateNavigationItem(string content, Symbol symbol, string tag)
    {
        return new NavigationViewItem
        {
            Content = content,
            Tag = tag,
            Icon = new SymbolIcon(symbol),
        };
    }

    private Grid BuildTitleBar()
    {
        var titleBar = new Grid { Margin = new Thickness(0, 0, 0, 20) };
        titleBar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        titleBar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var titleStack = new StackPanel { Spacing = 4, MinWidth = 0 };
        titleStack.Children.Add(new TextBlock
        {
            Text = "Kindle EPUB Fixer",
            Style = (Style)Application.Current.Resources["TitleTextBlockStyle"],
            FontSize = 30,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            TextTrimming = TextTrimming.CharacterEllipsis,
        });
        titleStack.Children.Add(new TextBlock
        {
            Text = "Kindle / Send to Kindle EPUB 修复工具，尽量保留原书排版语义。",
            Foreground = (Brush)Application.Current.Resources["MutedTextBrush"],
            TextTrimming = TextTrimming.CharacterEllipsis,
        });
        titleBar.Children.Add(titleStack);

        var statusStack = new StackPanel
        {
            HorizontalAlignment = HorizontalAlignment.Right,
            Spacing = 4,
        };
        statusStack.Children.Add(new TextBlock
        {
            Text = "v1.4.0-beta.1",
            Foreground = (Brush)Application.Current.Resources["MutedTextBrush"],
            HorizontalAlignment = HorizontalAlignment.Right,
        });
        StatusText = new TextBlock
        {
            Text = "准备就绪",
            Foreground = (Brush)Application.Current.Resources["MutedTextBrush"],
            HorizontalAlignment = HorizontalAlignment.Right,
        };
        statusStack.Children.Add(StatusText);
        Grid.SetColumn(statusStack, 1);
        titleBar.Children.Add(statusStack);
        return titleBar;
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
        if (args.SelectedItem is not NavigationViewItem item || item.Tag is not string tag)
        {
            return;
        }

        ShowPage(tag);
    }

    private void ShowPage(string tag)
    {
        ContentHost.Children.Clear();
        switch (tag)
        {
            case "Settings":
                _settingsPage ??= new SettingsPage();
                ContentHost.Children.Add(_settingsPage);
                break;
            case "About":
                _aboutPage ??= new AboutPage();
                ContentHost.Children.Add(_aboutPage);
                break;
            default:
                _homePage ??= CreateHomePage();
                ContentHost.Children.Add(_homePage);
                break;
        }
    }

    private HomePage CreateHomePage()
    {
        var page = new HomePage();
        page.StatusChanged += HomePage_StatusChanged;
        return page;
    }

    private void HomePage_StatusChanged(object? sender, string status)
    {
        StatusText.Text = status;
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

    private void ApplyNavigationPaneBackground()
    {
        var paneBrush = new AcrylicBrush
        {
            TintColor = Microsoft.UI.ColorHelper.FromArgb(255, 244, 247, 245),
            TintOpacity = 0.72,
            TintLuminosityOpacity = 0.86,
        };
        if (FindVisualChild<SplitView>(RootNav) is { } splitView)
        {
            splitView.PaneBackground = paneBrush;
            splitView.BorderThickness = new Thickness(0);
            splitView.BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
            splitView.CornerRadius = new CornerRadius(0);
        }

        if (FindVisualChild<Grid>(RootNav, "PaneContentGrid") is { } paneContent)
        {
            paneContent.Background = paneBrush;
            paneContent.BorderThickness = new Thickness(0);
            paneContent.BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        }

        if (FindVisualChild<Grid>(RootNav, "PaneContentGridToggleButtonRow") is { } toggleRow)
        {
            toggleRow.Background = paneBrush;
        }

        if (FindVisualChild<Grid>(RootNav, "PaneRoot") is { } paneRoot)
        {
            paneRoot.Background = paneBrush;
            paneRoot.CornerRadius = new CornerRadius(0);
        }

        if (FindVisualChild<Grid>(RootNav, "ContentGrid") is { } contentGrid)
        {
            contentGrid.Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        }
    }

    private static T? FindVisualChild<T>(DependencyObject root, string? name = null) where T : FrameworkElement
    {
        var count = VisualTreeHelper.GetChildrenCount(root);
        for (var i = 0; i < count; i++)
        {
            var child = VisualTreeHelper.GetChild(root, i);
            if (child is T typed && (name is null || typed.Name == name))
            {
                return typed;
            }

            var result = FindVisualChild<T>(child, name);
            if (result is not null)
            {
                return result;
            }
        }

        return null;
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
