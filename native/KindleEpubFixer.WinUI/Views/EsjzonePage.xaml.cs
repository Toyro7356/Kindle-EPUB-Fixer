using KindleEpubFixer.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace KindleEpubFixer.WinUI.Views;

public sealed partial class EsjzonePage : UserControl
{
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

        if (!Uri.TryCreate(url, UriKind.Absolute, out var parsed) || !parsed.Host.EndsWith("esjzone.one", StringComparison.OrdinalIgnoreCase))
        {
            App.MainWindowInstance?.ShowNotification("地址无效", "请使用 ESJZone 详情页地址。", InfoBarSeverity.Warning);
            return;
        }

        if (!TryGetMaxChapters(out var maxChapters))
        {
            App.MainWindowInstance?.ShowNotification("章节数无效", "请输入正整数或留空。", InfoBarSeverity.Warning);
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
