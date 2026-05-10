using KindleEpubFixer.WinUI.Services;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace KindleEpubFixer.WinUI.Views;

public sealed partial class EsjzonePage : UserControl
{
    private const string DefaultEsjzoneBaseUrl = "https://www.esjzone.cc/";
    private const string LegacyEsjzoneBaseUrl = "https://www.esjzone.one/";

    private readonly BackendRunner _backend = new();
    private readonly SettingsStore _settings = new();
    private CancellationTokenSource? _cancellation;
    private bool _isRunning;

    public EsjzonePage()
    {
        InitializeComponent();
        RefreshSettings();
        UpdateStartButton();
    }

    public event EventHandler<string>? StatusChanged;

    public void RefreshSettings()
    {
        _settings.LoadAppSettings();
        if (string.IsNullOrWhiteSpace(OutputDirBox.Text))
        {
            OutputDirBox.Text = _settings.DefaultOutputDirectory;
        }
    }

    private async void BrowseOutput_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FolderPicker();
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(App.MainWindowInstance));

        var folder = await picker.PickSingleFolderAsync();
        if (folder is not null)
        {
            OutputDirBox.Text = folder.Path;
        }
    }

    private async void StartButton_Click(object sender, RoutedEventArgs e)
    {
        if (_isRunning)
        {
            _cancellation?.Cancel();
            StatusChanged?.Invoke(this, "正在取消");
            return;
        }

        var url = UrlBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(url))
        {
            App.MainWindowInstance?.ShowNotification("请输入 ESJZone 地址", null, InfoBarSeverity.Warning);
            return;
        }

        if (!IsSupportedEsjzoneUrl(url))
        {
            App.MainWindowInstance?.ShowNotification("地址无效", "请使用 ESJZone 详情页地址。", InfoBarSeverity.Warning);
            return;
        }

        if (!TryGetMaxChapters(out var maxChapters))
        {
            App.MainWindowInstance?.ShowNotification("章节数无效", "留空会自动抓取全部章节；只测试前几章时再输入正整数。", InfoBarSeverity.Warning);
            return;
        }

        _isRunning = true;
        _cancellation = new CancellationTokenSource();
        SetStartButton(cancelMode: true);
        Progress.Value = 0;
        LogBox.Text = string.Empty;
        OutputText.Text = string.Empty;
        StatusChanged?.Invoke(this, "ESJZone 转制中");

        try
        {
            var output = await _backend.BuildEsjzoneAsync(
                url,
                string.IsNullOrWhiteSpace(OutputDirBox.Text) ? null : OutputDirBox.Text.Trim(),
                CookieBox.Text,
                maxChapters,
                AppendLog,
                progress => DispatcherQueue.TryEnqueue(() =>
                {
                    if (!string.IsNullOrWhiteSpace(progress.Status))
                    {
                        StatusChanged?.Invoke(this, progress.Status);
                    }

                    Progress.Value = progress.Progress;
                    if (!string.IsNullOrWhiteSpace(progress.Output))
                    {
                        OutputText.Text = progress.Output;
                    }
                }),
                _cancellation.Token);

            OutputText.Text = output;
            Progress.Value = 100;
            StatusChanged?.Invoke(this, "ESJZone 转制完成");
            App.MainWindowInstance?.ShowNotification("转制完成", output, InfoBarSeverity.Success);
        }
        catch (OperationCanceledException)
        {
            StatusChanged?.Invoke(this, "任务已取消");
            App.MainWindowInstance?.ShowNotification("任务已取消", null, InfoBarSeverity.Warning);
        }
        catch (Exception exc)
        {
            AppendLog($"错误: {exc.Message}");
            StatusChanged?.Invoke(this, "ESJZone 转制失败");
            App.MainWindowInstance?.ShowNotification("转制失败", exc.Message, InfoBarSeverity.Error);
        }
        finally
        {
            _isRunning = false;
            SetStartButton(cancelMode: false);
            _cancellation?.Dispose();
            _cancellation = null;
        }
    }

    private void AppendLog(string message)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            if (!string.IsNullOrEmpty(LogBox.Text))
            {
                LogBox.Text += Environment.NewLine;
            }

            LogBox.Text += message;
        });
    }

    private bool TryGetMaxChapters(out int? maxChapters)
    {
        maxChapters = null;
        var text = MaxChaptersBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return true;
        }

        if (int.TryParse(text, out var value) && value > 0)
        {
            maxChapters = value;
            return true;
        }

        return false;
    }

    private static bool IsSupportedEsjzoneUrl(string url)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var parsed))
        {
            return false;
        }

        var host = parsed.Host.ToLowerInvariant();
        return host == "www.esjzone.cc"
            || host == "esjzone.cc"
            || host == "www.esjzone.one"
            || host == "esjzone.one";
    }

    private async void Login_Click(object sender, RoutedEventArgs e)
    {
        var webView = new WebView2
        {
            Width = 920,
            Height = 620,
            Source = new Uri(DefaultEsjzoneBaseUrl + "my/profile.html"),
        };
        var statusText = new TextBlock
        {
            Text = "登录完成后会自动读取 Cookie，也可以点击“获取 Cookie”。",
            TextWrapping = TextWrapping.Wrap,
            Foreground = Application.Current.Resources["MutedTextBrush"] as Microsoft.UI.Xaml.Media.Brush,
        };
        var content = new Grid { RowSpacing = 10 };
        content.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        content.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        content.Children.Add(statusText);
        Grid.SetRow(webView, 1);
        content.Children.Add(webView);

        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "ESJZone 网页登录",
            Content = content,
            PrimaryButtonText = "获取 Cookie",
            SecondaryButtonText = "打开 .one",
            CloseButtonText = "关闭",
            DefaultButton = ContentDialogButton.Primary,
        };

        DispatcherQueueTimer? autoCloseTimer = null;

        async Task<bool> CaptureCookiesAsync(bool notify, bool requireLoggedIn)
        {
            try
            {
                await webView.EnsureCoreWebView2Async();
                if (requireLoggedIn && !await LooksLoggedInAsync(webView))
                {
                    statusText.Text = "等待登录完成。登录成功后会自动读取 Cookie。";
                    return false;
                }

                var cookieText = await ReadCookieHeaderAsync(webView);
                if (string.IsNullOrWhiteSpace(cookieText))
                {
                    if (notify)
                    {
                        statusText.Text = "还没有读取到 Cookie，请确认页面已经完成登录。";
                    }
                    return false;
                }

                CookieBox.Text = cookieText;
                statusText.Text = "已读取 Cookie。窗口会自动关闭。";
                if (notify)
                {
                    App.MainWindowInstance?.ShowNotification("已获取 ESJZone Cookie", null, InfoBarSeverity.Success);
                }

                autoCloseTimer ??= DispatcherQueue.CreateTimer();
                autoCloseTimer.Interval = TimeSpan.FromMilliseconds(450);
                autoCloseTimer.Tick += (_, _) =>
                {
                    autoCloseTimer.Stop();
                    dialog.Hide();
                };
                autoCloseTimer.Start();
                return true;
            }
            catch (Exception exc)
            {
                statusText.Text = $"读取 Cookie 失败：{exc.Message}";
                return false;
            }
        }

        webView.NavigationCompleted += async (_, _) =>
        {
            if (webView.Source is null)
            {
                return;
            }

            if (webView.Source.Host.EndsWith("esjzone.cc", StringComparison.OrdinalIgnoreCase)
                || webView.Source.Host.EndsWith("esjzone.one", StringComparison.OrdinalIgnoreCase))
            {
                await CaptureCookiesAsync(notify: false, requireLoggedIn: true);
            }
        };

        dialog.PrimaryButtonClick += async (_, args) =>
        {
            var deferral = args.GetDeferral();
            args.Cancel = !await CaptureCookiesAsync(notify: true, requireLoggedIn: false);
            deferral.Complete();
        };
        dialog.SecondaryButtonClick += (_, args) =>
        {
            args.Cancel = true;
            webView.Source = new Uri(LegacyEsjzoneBaseUrl + "my/profile.html");
            statusText.Text = "已切换到 .one 登录页。登录完成后会自动读取 Cookie。";
        };

        await dialog.ShowAsync();
        autoCloseTimer?.Stop();
    }

    private static async Task<bool> LooksLoggedInAsync(WebView2 webView)
    {
        try
        {
            await webView.EnsureCoreWebView2Async();
            var result = await webView.ExecuteScriptAsync(
                "Boolean(document.querySelector('a[href*=logout],a[href*=Logout],a[href*=logout]'))"
                + "||((document.body&&document.body.innerText||'').match(/登出|退出|個人中心|个人中心|profile/i)!=null"
                + "&&(document.body&&document.body.innerText||'').match(/login|登入|登录/i)==null)");
            return JsonSerializer.Deserialize<bool>(result);
        }
        catch
        {
            return false;
        }
    }

    private static async Task<string> ReadCookieHeaderAsync(WebView2 webView)
    {
        await webView.EnsureCoreWebView2Async();
        var manager = webView.CoreWebView2.CookieManager;
        var cookies = new List<Microsoft.Web.WebView2.Core.CoreWebView2Cookie>();
        cookies.AddRange(await manager.GetCookiesAsync(DefaultEsjzoneBaseUrl));
        cookies.AddRange(await manager.GetCookiesAsync(LegacyEsjzoneBaseUrl));

        return string.Join(
            "; ",
            cookies
                .GroupBy(cookie => cookie.Name)
                .Select(group => group.First())
                .Where(cookie => !string.IsNullOrWhiteSpace(cookie.Name))
                .Select(cookie => $"{cookie.Name}={cookie.Value}"));
    }

    private void Input_TextChanged(object sender, TextChangedEventArgs e)
    {
        UpdateStartButton();
    }

    private void UpdateStartButton()
    {
        StartButton.IsEnabled = _isRunning || !string.IsNullOrWhiteSpace(UrlBox.Text);
    }

    private void SetStartButton(bool cancelMode)
    {
        StartButton.Content = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = 8,
            Children =
            {
                new FontIcon { Glyph = cancelMode ? "\uE711" : "\uE768", FontSize = 15 },
                new TextBlock { Text = cancelMode ? "取消转制" : "开始转制", VerticalAlignment = VerticalAlignment.Center },
            },
        };
    }
}
