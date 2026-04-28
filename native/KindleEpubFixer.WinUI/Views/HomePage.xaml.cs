using System.Collections.ObjectModel;
using KindleEpubFixer.WinUI.Models;
using KindleEpubFixer.WinUI.Services;
using KindleEpubFixer.WinUI.ViewModels;
using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Windows.Storage.Pickers;
using WinRT.Interop;
using Path = System.IO.Path;

namespace KindleEpubFixer.WinUI.Views;

public sealed partial class HomePage : UserControl
{
    private const double MinNameColumnWidth = 80;
    private const double MinSourceColumnWidth = 70;
    private const double MinStatusColumnWidth = 48;
    private const double ActionColumnWidth = 56;
    private const double ResizeHandleWidth = 12;

    private readonly BackendRunner _backend = new();
    private readonly SettingsStore _settings = new();
    private readonly List<Grid> _rowGrids = new();
    private CancellationTokenSource? _cancellation;
    private bool _isRunning;
    private bool _updatingSelection;
    private double _nameColumnWidth = 220;
    private double _sourceColumnWidth = 180;
    private double _statusColumnWidth = 112;
    private readonly InputCursor _resizeCursor = InputSystemCursor.Create(InputSystemCursorShape.SizeWestEast);

    public HomePage()
    {
        InitializeComponent();
        RefreshSettings();
        UpdateHeaderCheckBox();
    }

    public event EventHandler<string>? StatusChanged;

    public HomePageViewModel ViewModel { get; } = new();

    public ObservableCollection<EpubTask> Tasks => ViewModel.Tasks;

    private string OutputHintTextValue => string.IsNullOrWhiteSpace(_settings.DefaultOutputDirectory)
        ? "默认保存到：每本书所在目录下的“转换后”文件夹"
        : $"默认保存到：{_settings.DefaultOutputDirectory}";

    public void RefreshSettings()
    {
        _settings.LoadAppSettings();
        OutputHintText.Text = OutputHintTextValue;
    }

    private async void AddFiles_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        picker.FileTypeFilter.Add(".epub");
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(App.MainWindowInstance));

        var files = await picker.PickMultipleFilesAsync();
        foreach (var file in files)
        {
            if (ViewModel.AddFile(file.Path))
            {
                UpdateHeaderCheckBox();
            }
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

        if (Tasks.Count == 0)
        {
            await ShowMessageAsync("请先添加 EPUB", string.Empty, InfoBarSeverity.Warning);
            return;
        }

        _settings.LoadAppSettings();
        OutputHintText.Text = OutputHintTextValue;
        _isRunning = true;
        _cancellation = new CancellationTokenSource();
        SetStartButton(cancelMode: true);
        OverallProgress.Value = 0;
        StatusChanged?.Invoke(this, "处理中");

        var total = Tasks.Count;
        var success = 0;
        for (var i = 0; i < total; i++)
        {
            if (_cancellation.IsCancellationRequested)
            {
                break;
            }

            var task = Tasks[i];
            try
            {
                task.Status = "处理中";
                task.Progress = 3;
                StatusChanged?.Invoke(this, $"处理中 {i + 1}/{total}: {task.Name}");

                var output = await _backend.ProcessAsync(
                    task.FilePath,
                    _settings.DefaultOutputDirectory,
                    message => DispatcherQueue.TryEnqueue(() => task.Logs.Add(message)),
                    progress => DispatcherQueue.TryEnqueue(() =>
                    {
                        if (!string.IsNullOrWhiteSpace(progress.Status))
                        {
                            task.Status = progress.Status;
                        }

                        task.Progress = progress.Progress;
                        task.Logs.Add($"{task.Status} {task.Progress}%");
                        if (!string.IsNullOrWhiteSpace(progress.Output))
                        {
                            task.Output = progress.Output;
                            task.Logs.Add($"输出: {progress.Output}");
                        }
                    }),
                    _cancellation.Token);

                task.Output = output;
                task.Status = "完成";
                task.Progress = 100;
                success++;
            }
            catch (OperationCanceledException)
            {
                task.Status = "已取消";
            }
            catch (Exception exc)
            {
                task.Logs.Add($"错误: {exc.Message}");
                task.Status = "失败";
                task.Progress = 100;
            }

            OverallProgress.Value = Math.Round(((double)(i + 1) / total) * 100);
        }

        _isRunning = false;
        SetStartButton(cancelMode: false);
        if (_cancellation.IsCancellationRequested)
        {
            StatusChanged?.Invoke(this, "任务已取消");
            await ShowMessageAsync("任务已取消", $"已完成 {success} / {total} 本。", InfoBarSeverity.Warning);
        }
        else
        {
            StatusChanged?.Invoke(this, "处理完成");
            OverallProgress.Value = 100;
            await ShowMessageAsync("处理完成", $"成功 {success} / {total} 本。", InfoBarSeverity.Success);
        }

        _cancellation.Dispose();
        _cancellation = null;
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
                new TextBlock { Text = cancelMode ? "取消处理" : "开始处理", VerticalAlignment = VerticalAlignment.Center },
            },
        };
    }

    private void SelectAll_Click(object sender, RoutedEventArgs e)
    {
        ViewModel.ToggleAll();
        UpdateHeaderCheckBox();
    }

    private void RemoveSelected_Click(object sender, RoutedEventArgs e)
    {
        if (_isRunning)
        {
            _ = ShowMessageAsync("正在处理", "稍后再删除任务。", InfoBarSeverity.Warning);
            return;
        }

        ViewModel.RemoveSelected();
        UpdateHeaderCheckBox();
    }

    private void ClearList_Click(object sender, RoutedEventArgs e)
    {
        if (_isRunning)
        {
            _ = ShowMessageAsync("正在处理", "稍后再清空列表。", InfoBarSeverity.Warning);
            return;
        }

        ViewModel.Clear();
        OverallProgress.Value = 0;
        UpdateHeaderCheckBox();
    }

    private void OpenOutput_Click(object sender, RoutedEventArgs e)
    {
        _settings.LoadAppSettings();
        OutputHintText.Text = OutputHintTextValue;
        var outputDirectory = _settings.DefaultOutputDirectory;
        if (!string.IsNullOrWhiteSpace(outputDirectory) && Directory.Exists(outputDirectory))
        {
            _ = Windows.System.Launcher.LaunchFolderPathAsync(outputDirectory);
            return;
        }

        var firstOutput = Tasks.Select(task => task.Output).FirstOrDefault(path => !string.IsNullOrWhiteSpace(path) && File.Exists(path));
        if (!string.IsNullOrWhiteSpace(firstOutput))
        {
            _ = Windows.System.Launcher.LaunchFolderPathAsync(Path.GetDirectoryName(firstOutput)!);
            return;
        }

        var firstTask = Tasks.FirstOrDefault();
        if (firstTask is not null)
        {
            var defaultOutput = Path.Combine(Path.GetDirectoryName(firstTask.FilePath)!, "转换后");
            if (Directory.Exists(defaultOutput))
            {
                _ = Windows.System.Launcher.LaunchFolderPathAsync(defaultOutput);
                return;
            }
        }

        _ = ShowMessageAsync("还没有输出目录", string.Empty, InfoBarSeverity.Warning);
    }

    private void HeaderCheckBox_Changed(object sender, RoutedEventArgs e)
    {
        if (_updatingSelection)
        {
            return;
        }

        var selectAll = HeaderCheckBox.IsChecked == true;
        foreach (var task in Tasks)
        {
            task.IsSelected = selectAll;
        }

        ViewModel.RefreshSummary();
        UpdateHeaderCheckBox();
    }

    private void TaskCheckBox_Changed(object sender, RoutedEventArgs e)
    {
        ViewModel.RefreshSummary();
        UpdateHeaderCheckBox();
    }

    private void ShowLog_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: string id } button)
        {
            var task = Tasks.FirstOrDefault(task => task.Id == id);
            if (task is not null)
            {
                ShowTaskLogFlyout(task, button);
            }
        }
    }

    private void Root_SizeChanged(object sender, SizeChangedEventArgs e)
    {
        FitColumnsToAvailableWidth();
        ApplyColumnWidths();
    }

    private void TaskTable_SizeChanged(object sender, RoutedEventArgs e)
    {
        FitColumnsToAvailableWidth();
        ApplyColumnWidths();
    }

    private void TaskList_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
    {
        args.ItemContainer.Padding = new Thickness(0);
        args.ItemContainer.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        args.ItemContainer.MinHeight = 50;
    }

    private void TaskRow_Loaded(object sender, RoutedEventArgs e)
    {
        if (sender is Grid grid && !_rowGrids.Contains(grid))
        {
            _rowGrids.Add(grid);
            ApplyColumnWidths(grid);
        }
    }

    private void TaskRow_Unloaded(object sender, RoutedEventArgs e)
    {
        if (sender is Grid grid)
        {
            _rowGrids.Remove(grid);
        }
    }

    private void ColumnThumb_PointerEntered(object sender, PointerRoutedEventArgs e)
    {
        ProtectedCursor = _resizeCursor;
    }

    private void ColumnThumb_PointerExited(object sender, PointerRoutedEventArgs e)
    {
        ProtectedCursor = null;
    }

    private void ColumnThumb_DragStarted(object sender, DragStartedEventArgs e)
    {
        ProtectedCursor = _resizeCursor;
    }

    private void ColumnThumb_DragCompleted(object sender, DragCompletedEventArgs e)
    {
        ProtectedCursor = null;
    }

    private void ColumnThumb_DragDelta(object sender, DragDeltaEventArgs e)
    {
        if (sender is not Thumb { Tag: string column })
        {
            return;
        }

        var delta = e.HorizontalChange;
        switch (column)
        {
            case "name-source":
                delta = Math.Clamp(delta, MinNameColumnWidth - _nameColumnWidth, _sourceColumnWidth - MinSourceColumnWidth);
                _nameColumnWidth += delta;
                _sourceColumnWidth -= delta;
                break;
            case "source-status":
                delta = Math.Clamp(delta, MinSourceColumnWidth - _sourceColumnWidth, _statusColumnWidth - MinStatusColumnWidth);
                _sourceColumnWidth += delta;
                _statusColumnWidth -= delta;
                break;
        }

        ApplyColumnWidths();
    }

    private void FitColumnsToAvailableWidth()
    {
        var visibleWidth = ActualWidth > 0
            ? ActualWidth
            : TaskTableBorder.ActualWidth;
        if (TaskTableBorder.ActualWidth > 0)
        {
            visibleWidth = Math.Min(visibleWidth, TaskTableBorder.ActualWidth);
        }

        var available = visibleWidth - 24;
        if (available <= 0)
        {
            return;
        }

        var resizableWidth = available - 44 - (ResizeHandleWidth * 2) - ActionColumnWidth;
        var minimumResizableWidth = MinNameColumnWidth + MinSourceColumnWidth + MinStatusColumnWidth;
        if (resizableWidth <= minimumResizableWidth)
        {
            _nameColumnWidth = MinNameColumnWidth;
            _sourceColumnWidth = MinSourceColumnWidth;
            _statusColumnWidth = MinStatusColumnWidth;
            return;
        }

        FitResizableColumnsToTotal(resizableWidth);
    }

    private void FitResizableColumnsToTotal(double targetWidth)
    {
        var currentWidth = _nameColumnWidth + _sourceColumnWidth + _statusColumnWidth;
        if (currentWidth <= 0)
        {
            _nameColumnWidth = Math.Round(targetWidth * 0.45);
            _sourceColumnWidth = Math.Round(targetWidth * 0.38);
            _statusColumnWidth = targetWidth - _nameColumnWidth - _sourceColumnWidth;
            return;
        }

        _nameColumnWidth = Math.Max(MinNameColumnWidth, Math.Round(_nameColumnWidth / currentWidth * targetWidth));
        _sourceColumnWidth = Math.Max(MinSourceColumnWidth, Math.Round(_sourceColumnWidth / currentWidth * targetWidth));
        _statusColumnWidth = Math.Max(MinStatusColumnWidth, Math.Round(_statusColumnWidth / currentWidth * targetWidth));
        BalanceResizableColumns(targetWidth);
    }

    private void BalanceResizableColumns(double targetWidth)
    {
        var overflow = _nameColumnWidth + _sourceColumnWidth + _statusColumnWidth - targetWidth;
        while (overflow > 0.5)
        {
            var changed = false;
            if (_sourceColumnWidth > MinSourceColumnWidth)
            {
                var step = Math.Min(overflow, _sourceColumnWidth - MinSourceColumnWidth);
                _sourceColumnWidth -= step;
                overflow -= step;
                changed = true;
            }

            if (overflow > 0.5 && _nameColumnWidth > MinNameColumnWidth)
            {
                var step = Math.Min(overflow, _nameColumnWidth - MinNameColumnWidth);
                _nameColumnWidth -= step;
                overflow -= step;
                changed = true;
            }

            if (overflow > 0.5 && _statusColumnWidth > MinStatusColumnWidth)
            {
                var step = Math.Min(overflow, _statusColumnWidth - MinStatusColumnWidth);
                _statusColumnWidth -= step;
                overflow -= step;
                changed = true;
            }

            if (!changed)
            {
                break;
            }
        }

        var remaining = targetWidth - _nameColumnWidth - _sourceColumnWidth - _statusColumnWidth;
        if (remaining > 0.5)
        {
            _sourceColumnWidth += Math.Round(remaining * 0.55);
            _nameColumnWidth = targetWidth - _sourceColumnWidth - _statusColumnWidth;
        }
    }

    private void ApplyColumnWidths()
    {
        ApplyColumnWidths(HeaderGrid);
        foreach (var row in _rowGrids)
        {
            ApplyColumnWidths(row);
        }
    }

    private void ApplyColumnWidths(Grid grid)
    {
        if (grid.ColumnDefinitions.Count < 8)
        {
            return;
        }

        grid.ColumnDefinitions[1].Width = new GridLength(_nameColumnWidth);
        grid.ColumnDefinitions[3].Width = new GridLength(_sourceColumnWidth);
        grid.ColumnDefinitions[5].Width = new GridLength(_statusColumnWidth);
        grid.ColumnDefinitions[7].Width = new GridLength(ActionColumnWidth);
    }

    private void ShowTaskLogFlyout(EpubTask task, FrameworkElement target)
    {
        var flyout = new Flyout
        {
            Placement = Microsoft.UI.Xaml.Controls.Primitives.FlyoutPlacementMode.RightEdgeAlignedTop,
            Content = new StackPanel
            {
                Spacing = 10,
                Children =
                {
                    new TextBlock
                    {
                        Text = $"日志 - {task.Name}",
                        FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                        TextTrimming = TextTrimming.CharacterEllipsis,
                        MaxWidth = 520,
                    },
                    BuildLogViewer(task, 260, 420),
                },
            },
        };
        flyout.ShowAt(target);
    }

    private static ScrollViewer BuildLogViewer(EpubTask task, double minHeight, double maxHeight)
    {
        return new ScrollViewer
        {
            Content = new TextBlock
            {
                Text = task.Logs.Count == 0 ? "暂无日志。此任务还没有开始处理。" : string.Join(Environment.NewLine, task.Logs),
                TextWrapping = TextWrapping.NoWrap,
                IsTextSelectionEnabled = true,
            },
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            MinHeight = minHeight,
            MaxHeight = maxHeight,
            MinWidth = 420,
            MaxWidth = 620,
        };
    }

    private Task ShowMessageAsync(string title, string message, InfoBarSeverity severity = InfoBarSeverity.Informational)
    {
        App.MainWindowInstance?.ShowNotification(title, message, severity);
        return Task.CompletedTask;
    }

    private void UpdateHeaderCheckBox()
    {
        _updatingSelection = true;
        try
        {
            HeaderCheckBox.IsThreeState = true;
            HeaderCheckBox.IsChecked = Tasks.Count == 0
                ? false
                : Tasks.All(task => task.IsSelected)
                    ? true
                    : Tasks.Any(task => task.IsSelected)
                        ? null
                        : false;
        }
        finally
        {
            _updatingSelection = false;
        }
    }
}
