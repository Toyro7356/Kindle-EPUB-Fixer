using KindleEpubFixer.WinUI.Services;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace KindleEpubFixer.WinUI.Views;

public sealed partial class EsjzonePage : UserControl
{
    private const int MaxLogLines = 2000;
    private const int MaxLogFlushLines = 250;

    private static readonly SourceConfig EsjzoneConfig = new(
        "esjzone",
        "ESJZone",
        "https://www.esjzone.cc/detail/...",
        "https://www.esjzone.cc/my/profile.html",
        "https://www.esjzone.one/my/profile.html",
        ["https://www.esjzone.cc/", "https://www.esjzone.one/"],
        ["esjzone.cc", "www.esjzone.cc", "esjzone.one", "www.esjzone.one"]);

    private static readonly SourceConfig MasiroConfig = new(
        "masiro",
        "Masiro",
        "https://masiro.me/admin/novelView?novel_id=...",
        "https://masiro.me/admin",
        null,
        ["https://masiro.me/", "https://www.masiro.me/"],
        ["masiro.me", "www.masiro.me", "masi.ro", "www.masi.ro"]);

    private readonly BackendRunner _backend = new();
    private readonly SettingsStore _settings = new();
    private readonly SourceConfig _source;
    private readonly object _logLock = new();
    private readonly Queue<string> _pendingLogLines = new();
    private readonly List<string> _logLines = new();
    private readonly DispatcherQueueTimer _logFlushTimer;
    private CancellationTokenSource? _cancellation;
    private bool _isRunning;
    private bool _isLoadingSettings;
    private string _userAgent = string.Empty;

    public EsjzonePage()
        : this(EsjzoneConfig)
    {
    }

    public static EsjzonePage CreateMasiroPage() => new(MasiroConfig);

    private EsjzonePage(SourceConfig source)
    {
        _source = source;
        InitializeComponent();
        UrlBox.PlaceholderText = source.UrlPlaceholder;
        AutoPurchaseBox.Visibility = source.SourceId == "masiro" ? Visibility.Visible : Visibility.Collapsed;
        _logFlushTimer = DispatcherQueue.CreateTimer();
        _logFlushTimer.Interval = TimeSpan.FromMilliseconds(120);
        _logFlushTimer.Tick += (_, _) => FlushPendingLogs(MaxLogFlushLines);
        RefreshSettings();
        UpdateStartButton();
    }

    public event EventHandler<string>? StatusChanged;

    public void RefreshSettings()
    {
        _isLoadingSettings = true;
        _settings.LoadAppSettings();
        if (string.IsNullOrWhiteSpace(OutputDirBox.Text))
        {
            OutputDirBox.Text = _settings.DefaultOutputDirectory;
        }
        var rememberCookie = _source.SourceId == "masiro"
            ? _settings.RememberMasiroCookie
            : _settings.RememberEsjzoneCookie;
        RememberCookieBox.IsChecked = rememberCookie;
        if (rememberCookie && string.IsNullOrWhiteSpace(CookieBox.Text))
        {
            CookieBox.Text = _source.SourceId == "masiro"
                ? _settings.MasiroCookie
                : _settings.EsjzoneCookie;
        }
        _userAgent = _source.SourceId == "masiro" ? _settings.MasiroUserAgent : string.Empty;
        _isLoadingSettings = false;
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
            App.MainWindowInstance?.ShowNotification($"请输入 {_source.DisplayName} 地址", null, InfoBarSeverity.Warning);
            return;
        }

        if (!IsSupportedSourceUrl(url))
        {
            App.MainWindowInstance?.ShowNotification("地址无效", $"请使用 {_source.DisplayName} 详情页地址。", InfoBarSeverity.Warning);
            return;
        }

        if (!TryGetChapterSelection(out var maxChapters, out var chapterStart, out var chapterEnd))
        {
            App.MainWindowInstance?.ShowNotification("章节范围无效", "留空会抓取全部章节；可以输入 10 或 1-10。", InfoBarSeverity.Warning);
            return;
        }

        SaveCookiePreference();

        _isRunning = true;
        _cancellation = new CancellationTokenSource();
        SetStartButton(cancelMode: true);
        Progress.Value = 0;
        ClearLog();
        OutputText.Text = string.Empty;
        StatusChanged?.Invoke(this, $"{_source.DisplayName} 转制中");
        await Task.Yield();

        try
        {
            var autoPurchase = _source.SourceId == "masiro" && AutoPurchaseBox.IsChecked == true;
            int? approvedPurchaseCost = null;
            if (autoPurchase)
            {
                StatusChanged?.Invoke(this, "计算 Masiro 购买费用");
                var purchasePlan = await _backend.PreviewMasiroPurchaseAsync(
                    url,
                    CookieBox.Text,
                    _userAgent,
                    maxChapters,
                    chapterStart,
                    chapterEnd,
                    _cancellation.Token);
                if (purchasePlan.AccountBalance is not null && purchasePlan.TotalCost > purchasePlan.AccountBalance)
                {
                    throw new InvalidOperationException(
                        $"所选章节需要 {purchasePlan.TotalCost} 金币，当前余额为 {purchasePlan.AccountBalance} 金币。");
                }
                if (purchasePlan.ChapterCount > 0 && !await ConfirmPurchaseAsync(purchasePlan))
                {
                    StatusChanged?.Invoke(this, "已取消自动购买");
                    return;
                }
                approvedPurchaseCost = purchasePlan.TotalCost;
            }

            var output = await _backend.BuildNovelAsync(
                _source.SourceId,
                url,
                string.IsNullOrWhiteSpace(OutputDirBox.Text) ? null : OutputDirBox.Text.Trim(),
                CookieBox.Text,
                _userAgent,
                autoPurchase,
                approvedPurchaseCost,
                maxChapters,
                chapterStart,
                chapterEnd,
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

            FlushPendingLogs();
            OutputText.Text = output;
            Progress.Value = 100;
            StatusChanged?.Invoke(this, $"{_source.DisplayName} 转制完成");
            App.MainWindowInstance?.ShowNotification("转制完成", output, InfoBarSeverity.Success);
        }
        catch (OperationCanceledException)
        {
            FlushPendingLogs();
            StatusChanged?.Invoke(this, "任务已取消");
            App.MainWindowInstance?.ShowNotification("任务已取消", null, InfoBarSeverity.Warning);
        }
        catch (Exception exc)
        {
            AppendLog($"错误: {exc.Message}");
            StatusChanged?.Invoke(this, $"{_source.DisplayName} 转制失败");
            App.MainWindowInstance?.ShowNotification("转制失败", exc.Message, InfoBarSeverity.Error);
        }
        finally
        {
            FlushPendingLogs();
            _isRunning = false;
            SetStartButton(cancelMode: false);
            AutoPurchaseBox.IsChecked = false;
            _cancellation?.Dispose();
            _cancellation = null;
        }
    }

    private async Task<bool> ConfirmPurchaseAsync(MasiroPurchasePlan plan)
    {
        var balanceText = plan.AccountBalance is null
            ? "未能读取当前余额。"
            : $"当前余额：{plan.AccountBalance} 金币。";
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "确认自动购买",
            Content = $"所选范围包含 {plan.ChapterCount} 个付费章节，预计总计 {plan.TotalCost} 金币。\n"
                + balanceText
                + "\n购买成功后无法由本工具撤销。后端将以本次总价作为硬预算上限，价格变化时会停止。",
            PrimaryButtonText = $"购买（{plan.TotalCost} 金币）",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    private void AppendLog(string message)
    {
        lock (_logLock)
        {
            _pendingLogLines.Enqueue(message);
        }

        DispatcherQueue.TryEnqueue(() =>
        {
            if (!_logFlushTimer.IsRunning)
            {
                _logFlushTimer.Start();
            }
        });
    }

    private void ClearLog()
    {
        _logFlushTimer.Stop();
        lock (_logLock)
        {
            _pendingLogLines.Clear();
            _logLines.Clear();
        }

        LogBox.Text = string.Empty;
    }

    private void FlushPendingLogs(int maxLines = int.MaxValue)
    {
        if (!DispatcherQueue.HasThreadAccess)
        {
            DispatcherQueue.TryEnqueue(() => FlushPendingLogs(maxLines));
            return;
        }

        List<string> batch = new();
        lock (_logLock)
        {
            while (_pendingLogLines.Count > 0 && batch.Count < maxLines)
            {
                batch.Add(_pendingLogLines.Dequeue());
            }

            if (_pendingLogLines.Count == 0)
            {
                _logFlushTimer.Stop();
            }
        }

        if (batch.Count == 0)
        {
            return;
        }

        _logLines.AddRange(batch);
        if (_logLines.Count > MaxLogLines)
        {
            _logLines.RemoveRange(0, _logLines.Count - MaxLogLines);
        }

        var builder = new StringBuilder();
        for (var i = 0; i < _logLines.Count; i++)
        {
            if (i > 0)
            {
                builder.AppendLine();
            }

            builder.Append(_logLines[i]);
        }

        LogBox.Text = builder.ToString();
        LogBox.SelectionStart = LogBox.Text.Length;
        LogBox.SelectionLength = 0;

        lock (_logLock)
        {
            if (_pendingLogLines.Count > 0 && !_logFlushTimer.IsRunning)
            {
                _logFlushTimer.Start();
            }
        }
    }

    private void RememberCookie_Changed(object sender, RoutedEventArgs e)
    {
        if (_isLoadingSettings)
        {
            return;
        }

        SaveCookiePreference();
    }

    private void SaveCookiePreference()
    {
        if (_source.SourceId == "masiro")
        {
            _settings.RememberMasiroCookie = RememberCookieBox.IsChecked == true;
            _settings.MasiroCookie = _settings.RememberMasiroCookie ? CookieBox.Text.Trim() : string.Empty;
            _settings.MasiroUserAgent = _settings.RememberMasiroCookie ? _userAgent : string.Empty;
        }
        else
        {
            _settings.RememberEsjzoneCookie = RememberCookieBox.IsChecked == true;
            _settings.EsjzoneCookie = _settings.RememberEsjzoneCookie ? CookieBox.Text.Trim() : string.Empty;
        }
        _settings.SaveAppSettings();
    }

    private bool TryGetChapterSelection(out int? maxChapters, out int? chapterStart, out int? chapterEnd)
    {
        maxChapters = null;
        chapterStart = null;
        chapterEnd = null;
        var text = MaxChaptersBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return true;
        }

        var singleMatch = Regex.Match(text, @"^(\d+)\s*(?:话|話|章|章节|章節)?$");
        if (singleMatch.Success && int.TryParse(singleMatch.Groups[1].Value, out var value) && value > 0)
        {
            maxChapters = value;
            return true;
        }

        var rangeMatch = Regex.Match(text, @"^(\d+)\s*(?:-|~|～|—|–|至|到)\s*(\d+)\s*(?:话|話|章|章节|章節)?$");
        if (!rangeMatch.Success
            || !int.TryParse(rangeMatch.Groups[1].Value, out var start)
            || !int.TryParse(rangeMatch.Groups[2].Value, out var end)
            || start <= 0
            || end < start)
        {
            return false;
        }

        chapterStart = start;
        chapterEnd = end;
        return true;
    }

    private bool IsSupportedSourceUrl(string url)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var parsed))
        {
            return false;
        }

        return _source.Hosts.Contains(parsed.Host, StringComparer.OrdinalIgnoreCase);
    }

    private async void Login_Click(object sender, RoutedEventArgs e)
    {
        var webView = new WebView2
        {
            Width = 920,
            Height = 620,
            Source = new Uri(_source.LoginUrl),
        };
        var statusText = new TextBlock
        {
            Text = "会自动读取当前 Cookie；如旧登录态已失效，请点击“重新登录”。",
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
            Title = $"{_source.DisplayName} 网页登录",
            Content = content,
            PrimaryButtonText = "获取 Cookie",
            SecondaryButtonText = _source.SourceId == "masiro"
                ? "重新登录"
                : _source.AlternateLoginUrl is null ? null : "打开 .one",
            CloseButtonText = "关闭",
            DefaultButton = ContentDialogButton.Primary,
        };

        DispatcherQueueTimer? autoCloseTimer = null;
        var hasSeenLoginPage = false;

        async Task<bool> CaptureCookiesAsync(bool notify, bool requireLoggedIn, bool autoClose)
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
                _userAgent = await ReadBrowserUserAgentAsync(webView);
                SaveCookiePreference();
                statusText.Text = autoClose
                    ? "已读取新的 Cookie。窗口会自动关闭。"
                    : "已刷新当前 Cookie。若请求仍被拒绝，请点击“重新登录”清除旧会话。";
                if (notify)
                {
                    App.MainWindowInstance?.ShowNotification($"已获取 {_source.DisplayName} Cookie", null, InfoBarSeverity.Success);
                }

                if (autoClose)
                {
                    autoCloseTimer ??= DispatcherQueue.CreateTimer();
                    autoCloseTimer.Interval = TimeSpan.FromMilliseconds(450);
                    autoCloseTimer.Tick += (_, _) =>
                    {
                        autoCloseTimer.Stop();
                        dialog.Hide();
                    };
                    autoCloseTimer.Start();
                }
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

            if (_source.Hosts.Contains(webView.Source.Host, StringComparer.OrdinalIgnoreCase))
            {
                if (!await LooksLoggedInAsync(webView))
                {
                    hasSeenLoginPage = true;
                    statusText.Text = "等待登录完成。成功后会自动读取新的 Cookie。";
                    return;
                }

                await CaptureCookiesAsync(
                    notify: false,
                    requireLoggedIn: false,
                    autoClose: hasSeenLoginPage);
            }
        };

        dialog.PrimaryButtonClick += async (_, args) =>
        {
            var deferral = args.GetDeferral();
            args.Cancel = !await CaptureCookiesAsync(notify: true, requireLoggedIn: false, autoClose: true);
            deferral.Complete();
        };
        dialog.SecondaryButtonClick += async (_, args) =>
        {
            args.Cancel = true;
            if (_source.SourceId == "masiro")
            {
                try
                {
                    await webView.EnsureCoreWebView2Async();
                    webView.CoreWebView2.CookieManager.DeleteAllCookies();
                    CookieBox.Text = string.Empty;
                    _userAgent = string.Empty;
                    SaveCookiePreference();
                    hasSeenLoginPage = true;
                    statusText.Text = "旧 Cookie 已清除，请在网页中重新登录。";
                    webView.CoreWebView2.Navigate(_source.LoginUrl);
                }
                catch (Exception exc)
                {
                    statusText.Text = $"清除旧登录态失败：{exc.Message}";
                }
            }
            else if (_source.AlternateLoginUrl is not null)
            {
                webView.Source = new Uri(_source.AlternateLoginUrl);
                statusText.Text = "已切换到备用登录页。登录完成后会自动读取 Cookie。";
            }
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

    private async Task<string> ReadCookieHeaderAsync(WebView2 webView)
    {
        await webView.EnsureCoreWebView2Async();
        var manager = webView.CoreWebView2.CookieManager;
        var cookies = new List<Microsoft.Web.WebView2.Core.CoreWebView2Cookie>();
        foreach (var baseUrl in _source.CookieBaseUrls)
        {
            cookies.AddRange(await manager.GetCookiesAsync(baseUrl));
        }

        return string.Join(
            "; ",
            cookies
                .GroupBy(cookie => cookie.Name)
                .Select(group => group.First())
                .Where(cookie => !string.IsNullOrWhiteSpace(cookie.Name))
                .Select(cookie => $"{cookie.Name}={cookie.Value}"));
    }

    private static async Task<string> ReadBrowserUserAgentAsync(WebView2 webView)
    {
        try
        {
            var result = await webView.ExecuteScriptAsync("navigator.userAgent");
            return JsonSerializer.Deserialize<string>(result) ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
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

    private sealed record SourceConfig(
        string SourceId,
        string DisplayName,
        string UrlPlaceholder,
        string LoginUrl,
        string? AlternateLoginUrl,
        string[] CookieBaseUrls,
        string[] Hosts);
}
