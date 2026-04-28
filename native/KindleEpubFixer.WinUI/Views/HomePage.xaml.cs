using System.Collections.ObjectModel;
using KindleEpubFixer.WinUI.Models;
using KindleEpubFixer.WinUI.Services;
using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;
using Microsoft.UI.Xaml.Shapes;
using Windows.Storage.Pickers;
using WinRT.Interop;
using Path = System.IO.Path;

namespace KindleEpubFixer.WinUI.Views;

public sealed partial class HomePage : UserControl
{
    private readonly BackendRunner _backend = new();
    private readonly SettingsStore _settings = new();
    private CancellationTokenSource? _cancellation;
    private int _taskSeq;
    private bool _isRunning;
    private Button StartButton = null!;
    private ProgressBar OverallProgress = null!;
    private TextBlock OutputHintText = null!;
    private TextBlock SummaryText = null!;
    private TextBlock SelectedSummaryText = null!;
    private ListView TaskList = null!;
    private CheckBox HeaderCheckBox = null!;
    private bool _updatingSelection;
    private Grid? _headerGrid;
    private Grid? _tableGrid;
    private ColumnResizeState? _resizeState;
    private readonly List<Grid> _rowGrids = new();
    private double _nameColumnWidth = 220;
    private double _sourceColumnWidth = 210;
    private double _statusColumnWidth = 104;
    private readonly Grid Root = new() { Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent) };

    public HomePage()
    {
        try
        {
            Content = Root;
            BuildLayout();
            _settings.LoadAppSettings();
            OutputHintText.Text = OutputHintTextValue;
        }
        catch (Exception exc)
        {
            File.AppendAllText(Path.Combine(AppContext.BaseDirectory, "home-crash.log"), $"{DateTimeOffset.Now:u} {exc}\n");
            throw;
        }
    }

    public event EventHandler<string>? StatusChanged;

    public ObservableCollection<EpubTask> Tasks { get; } = new();

    public ObservableCollection<FrameworkElement> TaskRows { get; } = new();

    private sealed record ColumnResizeState(int ColumnIndex, double StartX, double StartWidth);

    private sealed class ResizeHandle : Grid
    {
        public void UseResizeCursor(bool active)
        {
            ProtectedCursor = active ? InputSystemCursor.Create(InputSystemCursorShape.SizeWestEast) : null;
        }
    }

    private void BuildLayout()
    {
        Root.RowSpacing = 14;
        Root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        Root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        Root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        Root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        var toolbar = new Grid { ColumnSpacing = 12 };
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var addButton = CreateActionButton("添加 EPUB", "\uE8A5", AddFiles_Click, true);
        StartButton = CreateActionButton("开始处理", "\uE768", StartButton_Click, true);
        toolbar.Children.Add(addButton);
        AddToGrid(toolbar, StartButton, 2);
        Root.Children.Add(toolbar);

        var summaryGrid = new Grid { ColumnSpacing = 12 };
        summaryGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        summaryGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        summaryGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var summaryStack = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = 8,
            VerticalAlignment = VerticalAlignment.Center,
        };
        SummaryText = new TextBlock
        {
            Text = "0 本 EPUB",
            FontSize = 20,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            VerticalAlignment = VerticalAlignment.Center,
        };
        SelectedSummaryText = new TextBlock
        {
            FontSize = 14,
            Foreground = (Brush)Application.Current.Resources["MutedTextBrush"],
            VerticalAlignment = VerticalAlignment.Bottom,
        };
        summaryStack.Children.Add(SummaryText);
        summaryStack.Children.Add(SelectedSummaryText);
        var hint = new TextBlock
        {
            Text = "双击任务或点击信息图标查看日志",
            Foreground = (Brush)Application.Current.Resources["MutedTextBrush"],
            HorizontalAlignment = HorizontalAlignment.Right,
            VerticalAlignment = VerticalAlignment.Center,
        };
        var listCommands = CreateListCommandBar();
        summaryGrid.Children.Add(summaryStack);
        Grid.SetColumn(hint, 1);
        summaryGrid.Children.Add(hint);
        Grid.SetColumn(listCommands, 2);
        summaryGrid.Children.Add(listCommands);
        Grid.SetRow(summaryGrid, 1);
        Root.Children.Add(summaryGrid);

        var table = BuildTaskTable();
        Grid.SetRow(table, 2);
        Root.Children.Add(table);

        var footer = new StackPanel { Spacing = 8 };
        OverallProgress = new ProgressBar { Maximum = 100 };
        OutputHintText = new TextBlock { Foreground = (Brush)Application.Current.Resources["MutedTextBrush"] };
        footer.Children.Add(OverallProgress);
        footer.Children.Add(OutputHintText);
        Grid.SetRow(footer, 3);
        Root.Children.Add(footer);
    }

    private static Button CreateActionButton(string text, string glyph, RoutedEventHandler click, bool accent)
    {
        var button = new Button
        {
            Content = CreateButtonContent(text, glyph),
            MinWidth = 132,
            Height = 40,
            Padding = new Thickness(18, 0, 18, 0),
        };
        if (accent)
        {
            button.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
        }

        button.Click += click;
        return button;
    }

    private static StackPanel CreateButtonContent(string text, string glyph)
    {
        var content = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = 8,
            VerticalAlignment = VerticalAlignment.Center,
        };
        content.Children.Add(new FontIcon { Glyph = glyph, FontSize = 15 });
        content.Children.Add(new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center });
        return content;
    }

    private CommandBar CreateListCommandBar()
    {
        var commandBar = new CommandBar
        {
            DefaultLabelPosition = CommandBarDefaultLabelPosition.Right,
            IsOpen = false,
            Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
            Padding = new Thickness(0),
            HorizontalAlignment = HorizontalAlignment.Right,
        };

        commandBar.PrimaryCommands.Add(CreateCommand("全选", "\uE762", SelectAll_Click));
        commandBar.PrimaryCommands.Add(CreateCommand("删除", "\uE74D", RemoveSelected_Click));
        commandBar.PrimaryCommands.Add(CreateCommand("清空", "\uE894", ClearList_Click));
        commandBar.PrimaryCommands.Add(CreateCommand("输出目录", "\uE8B7", OpenOutput_Click));
        return commandBar;
    }

    private static AppBarButton CreateCommand(string label, string glyph, RoutedEventHandler click)
    {
        var button = new AppBarButton
        {
            Label = label,
            Icon = new FontIcon { Glyph = glyph },
            IsCompact = true,
        };
        button.Click += click;
        return button;
    }

    private static void AddToGrid(Grid grid, FrameworkElement element, int column)
    {
        Grid.SetColumn(element, column);
        grid.Children.Add(element);
    }

    private FrameworkElement BuildTaskTable()
    {
        var border = new Border
        {
            CornerRadius = new CornerRadius(6),
            Background = (Brush)Application.Current.Resources["CardBackgroundFillColorDefaultBrush"],
            BorderBrush = (Brush)Application.Current.Resources["SubtleBorderBrush"],
            BorderThickness = new Thickness(1),
        };

        var table = new Grid { MinWidth = GetTableWidth() };
        _tableGrid = table;
        table.RowDefinitions.Add(new RowDefinition { Height = new GridLength(40) });
        table.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        border.Child = table;

        var header = BuildTaskRowGrid();
        _headerGrid = header;
        header.Padding = new Thickness(12, 0, 12, 0);
        HeaderCheckBox = new CheckBox
        {
            Width = 32,
            Height = 32,
            Padding = new Thickness(0),
            VerticalAlignment = VerticalAlignment.Center,
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        HeaderCheckBox.Checked += HeaderCheckBox_Changed;
        HeaderCheckBox.Unchecked += HeaderCheckBox_Changed;
        HeaderCheckBox.Indeterminate += HeaderCheckBox_Changed;
        Grid.SetColumn(HeaderCheckBox, 0);
        header.Children.Add(HeaderCheckBox);
        AddHeaderText(header, "书名", 1, TextAlignment.Left);
        AddColumnResizer(header, 2, 1);
        AddHeaderText(header, "来源", 3, TextAlignment.Left);
        AddColumnResizer(header, 4, 3);
        AddHeaderText(header, "状态", 5, TextAlignment.Center);
        var headerBorder = new Border
        {
            BorderBrush = (Brush)Application.Current.Resources["SubtleBorderBrush"],
            BorderThickness = new Thickness(0, 0, 0, 1),
            Child = header,
        };
        table.Children.Add(headerBorder);

        TaskList = new ListView
        {
            ItemsSource = TaskRows,
            SelectionMode = ListViewSelectionMode.None,
            IsItemClickEnabled = false,
            Padding = new Thickness(0),
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
            ItemContainerTransitions = new TransitionCollection(),
        };
        TaskList.ContainerContentChanging += TaskList_ContainerContentChanging;
        TaskList.SizeChanged += (_, _) => SyncRowWidths();
        Grid.SetRow(TaskList, 1);
        table.Children.Add(TaskList);

        return new ScrollViewer
        {
            Content = border,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollMode = ScrollMode.Enabled,
            VerticalScrollBarVisibility = ScrollBarVisibility.Disabled,
        };
    }

    private Grid BuildTaskRowGrid()
    {
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(44) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(_nameColumnWidth) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(8) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(_sourceColumnWidth) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(8) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(_statusColumnWidth) });
        return grid;
    }

    private static void AddHeaderText(Grid grid, string text, int column, TextAlignment alignment)
    {
        var block = new TextBlock
        {
            Text = text,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            TextAlignment = alignment,
            VerticalAlignment = VerticalAlignment.Center,
        };
        Grid.SetColumn(block, column);
        grid.Children.Add(block);
    }

    private void AddColumnResizer(Grid grid, int visualColumn, int resizedColumn)
    {
        var line = new Rectangle
        {
            Width = 1,
            Fill = (Brush)Application.Current.Resources["ColumnDividerBrush"],
            Opacity = 0.22,
            HorizontalAlignment = HorizontalAlignment.Center,
        };
        var hitTarget = new ResizeHandle
        {
            Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
            Tag = resizedColumn,
            Children = { line },
        };
        hitTarget.PointerEntered += ColumnResizer_PointerEntered;
        hitTarget.PointerExited += ColumnResizer_PointerExited;
        hitTarget.PointerPressed += ColumnResizer_PointerPressed;
        hitTarget.PointerMoved += ColumnResizer_PointerMoved;
        hitTarget.PointerReleased += ColumnResizer_PointerReleased;
        hitTarget.PointerCanceled += ColumnResizer_PointerReleased;
        Grid.SetColumn(hitTarget, visualColumn);
        grid.Children.Add(hitTarget);
    }

    private Grid BuildTaskRow(EpubTask task)
    {
        var row = BuildTaskRowGrid();
        row.Tag = task;
        row.DataContext = task;
        row.MinHeight = 44;
        row.Padding = new Thickness(12, 0, 12, 0);
        row.DoubleTapped += TaskRow_DoubleTapped;

        var checkBox = new CheckBox
        {
            Width = 32,
            Height = 32,
            Padding = new Thickness(0),
            VerticalAlignment = VerticalAlignment.Center,
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        checkBox.SetBinding(CheckBox.IsCheckedProperty, new Binding
        {
            Path = new PropertyPath(nameof(EpubTask.IsSelected)),
            Mode = BindingMode.TwoWay,
        });
        checkBox.Checked += TaskCheckBox_Changed;
        checkBox.Unchecked += TaskCheckBox_Changed;
        Grid.SetColumn(checkBox, 0);
        row.Children.Add(checkBox);

        var nameCell = new Grid { ColumnSpacing = 8 };
        nameCell.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        nameCell.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.PointerEntered += TaskRow_PointerEntered;
        row.PointerExited += TaskRow_PointerExited;
        Grid.SetColumn(nameCell, 1);
        row.Children.Add(nameCell);
        AddBoundText(nameCell, "Name", 0, true, TextAlignment.Left);
        AddBoundText(row, "Folder", 3, false, TextAlignment.Left);
        AddBoundText(row, "StatusWithProgress", 5, true, TextAlignment.Center);

        var logButton = new Button
        {
            Width = 28,
            Height = 28,
            Padding = new Thickness(0),
            BorderThickness = new Thickness(1),
            BorderBrush = (Brush)Application.Current.Resources["SubtleBorderBrush"],
            Background = (Brush)Application.Current.Resources["CardBackgroundBrush"],
            CornerRadius = new CornerRadius(6),
            HorizontalAlignment = HorizontalAlignment.Right,
            VerticalAlignment = VerticalAlignment.Center,
            Content = new FontIcon { Glyph = "\uE946", FontSize = 13 },
            Opacity = 0.18,
            IsHitTestVisible = true,
            Tag = task.Id,
        };
        ToolTipService.SetToolTip(logButton, "查看日志");
        logButton.Click += ShowLog_Click;
        Grid.SetColumn(logButton, 1);
        nameCell.Children.Add(logButton);
        _rowGrids.Add(row);
        return row;
    }

    private void TaskRow_PointerEntered(object sender, PointerRoutedEventArgs e)
    {
        if (sender is FrameworkElement element && element.DataContext is EpubTask task)
        {
            SetRowLogButtonVisible(task, true);
        }
    }

    private void TaskRow_PointerExited(object sender, PointerRoutedEventArgs e)
    {
        if (sender is FrameworkElement element && element.DataContext is EpubTask task)
        {
            SetRowLogButtonVisible(task, false);
        }
    }

    private void SetRowLogButtonVisible(EpubTask task, bool visible)
    {
        var row = _rowGrids.FirstOrDefault(item => item.Tag == task);
        var button = row?.Children
            .OfType<Grid>()
            .SelectMany(child => child.Children.OfType<Button>())
            .FirstOrDefault(child => child.Tag is string);
        if (button is null)
        {
            return;
        }

        button.Opacity = visible ? 1 : 0.18;
        button.IsHitTestVisible = true;
    }

    private void ColumnResizer_PointerEntered(object sender, PointerRoutedEventArgs e)
    {
        if (sender is ResizeHandle target)
        {
            SetResizerVisual(target, true);
            target.UseResizeCursor(true);
        }
    }

    private void ColumnResizer_PointerExited(object sender, PointerRoutedEventArgs e)
    {
        if (sender is ResizeHandle target && _resizeState is null)
        {
            SetResizerVisual(target, false);
            target.UseResizeCursor(false);
        }
    }

    private void ColumnResizer_PointerPressed(object sender, PointerRoutedEventArgs e)
    {
        if (sender is not Grid target || target.Tag is not int columnIndex || _headerGrid is null)
        {
            return;
        }

        var startX = e.GetCurrentPoint(_headerGrid).Position.X;
        _resizeState = new ColumnResizeState(columnIndex, startX, GetResizableColumnWidth(columnIndex));
        target.CapturePointer(e.Pointer);
        SetResizerVisual(target, true);
        e.Handled = true;
    }

    private void ColumnResizer_PointerMoved(object sender, PointerRoutedEventArgs e)
    {
        if (_resizeState is null || _headerGrid is null)
        {
            return;
        }

        var currentX = e.GetCurrentPoint(_headerGrid).Position.X;
        var width = Math.Max(GetColumnMinimumWidth(_resizeState.ColumnIndex), _resizeState.StartWidth + currentX - _resizeState.StartX);
        SetResizableColumnWidth(_resizeState.ColumnIndex, width);
        ApplyColumnWidths();
        e.Handled = true;
    }

    private void ColumnResizer_PointerReleased(object sender, PointerRoutedEventArgs e)
    {
        if (sender is Grid target)
        {
            target.ReleasePointerCapture(e.Pointer);
            SetResizerVisual(target, false);
        }

        _resizeState = null;
    }

    private static void SetResizerVisual(Grid target, bool active)
    {
        if (target.Children.FirstOrDefault() is Rectangle line)
        {
            line.Fill = active
                ? (Brush)Application.Current.Resources["ColumnDividerHoverBrush"]
                : (Brush)Application.Current.Resources["ColumnDividerBrush"];
            line.Opacity = active ? 0.9 : 0.22;
            line.Width = active ? 2 : 1;
        }
    }

    private void TaskList_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
    {
        args.ItemContainer.Padding = new Thickness(0);
        args.ItemContainer.MinHeight = 44;
        args.ItemContainer.HorizontalContentAlignment = HorizontalAlignment.Stretch;
    }

    private void SyncRowWidths()
    {
        var width = Math.Max(GetTableWidth(), TaskList.ActualWidth);
        if (width <= 0)
        {
            return;
        }

        foreach (var row in TaskRows)
        {
            row.Width = width;
        }
    }

    private double GetTableWidth()
    {
        return 44 + _nameColumnWidth + 8 + _sourceColumnWidth + 8 + _statusColumnWidth + 24;
    }

    private double GetResizableColumnWidth(int columnIndex)
    {
        return columnIndex switch
        {
            1 => _nameColumnWidth,
            3 => _sourceColumnWidth,
            5 => _statusColumnWidth,
            _ => 120,
        };
    }

    private static double GetColumnMinimumWidth(int columnIndex)
    {
        return columnIndex switch
        {
            1 => 140,
            3 => 140,
            5 => 88,
            _ => 96,
        };
    }

    private void SetResizableColumnWidth(int columnIndex, double width)
    {
        switch (columnIndex)
        {
            case 1:
                _nameColumnWidth = width;
                break;
            case 3:
                _sourceColumnWidth = width;
                break;
            case 5:
                _statusColumnWidth = width;
                break;
        }
    }

    private void ApplyColumnWidths()
    {
        if (_headerGrid is not null)
        {
            ApplyColumnWidths(_headerGrid);
        }

        if (_tableGrid is not null)
        {
            _tableGrid.MinWidth = GetTableWidth();
        }

        foreach (var row in _rowGrids)
        {
            ApplyColumnWidths(row);
        }

        SyncRowWidths();
    }

    private void ApplyColumnWidths(Grid grid)
    {
        grid.ColumnDefinitions[1].Width = new GridLength(_nameColumnWidth);
        grid.ColumnDefinitions[3].Width = new GridLength(_sourceColumnWidth);
        grid.ColumnDefinitions[5].Width = new GridLength(_statusColumnWidth);
    }

    private static void AddBoundText(Grid row, string path, int column, bool semibold, TextAlignment alignment)
    {
        var block = new TextBlock
        {
            VerticalAlignment = VerticalAlignment.Center,
            TextTrimming = TextTrimming.CharacterEllipsis,
            TextAlignment = alignment,
            FontWeight = semibold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal,
        };
        if (!semibold)
        {
            block.Foreground = (Brush)Application.Current.Resources["MutedTextBrush"];
        }

        block.SetBinding(TextBlock.TextProperty, new Binding { Path = new PropertyPath(path) });
        Grid.SetColumn(block, column);
        row.Children.Add(block);
    }

    private string OutputHintTextValue => string.IsNullOrWhiteSpace(_settings.DefaultOutputDirectory)
        ? "默认保存到：每本书所在目录下的“转换后”文件夹"
        : $"默认保存到：{_settings.DefaultOutputDirectory}";

    private async void AddFiles_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        picker.FileTypeFilter.Add(".epub");
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(App.MainWindowInstance));
        var files = await picker.PickMultipleFilesAsync();
        foreach (var file in files)
        {
            AddFile(file.Path);
        }
    }

    private void AddFile(string path)
    {
        if (!path.EndsWith(".epub", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        var resolved = Path.GetFullPath(path);
        if (Tasks.Any(task => string.Equals(task.FilePath, resolved, StringComparison.OrdinalIgnoreCase)))
        {
            return;
        }

        var task = new EpubTask($"task-{++_taskSeq}", resolved);
        task.Logs.Add($"已添加: {resolved}");
        Tasks.Add(task);
        var row = BuildTaskRow(task);
        TaskRows.Add(row);
        SyncRowWidths();
        RefreshSummary();
        UpdateHeaderCheckBox();
    }

    private void RemoveSelected_Click(object sender, RoutedEventArgs e)
    {
        if (_isRunning)
        {
            _ = ShowMessageAsync("处理中", "处理过程中暂时不能删除任务。");
            return;
        }

        foreach (var task in Tasks.Where(task => task.IsSelected).ToList())
        {
            var row = TaskRows.FirstOrDefault(row => row.Tag == task);
            Tasks.Remove(task);
            if (row is not null)
            {
                TaskRows.Remove(row);
                if (row is Grid grid)
                {
                    _rowGrids.Remove(grid);
                }
            }
        }

        RefreshSummary();
        UpdateHeaderCheckBox();
    }

    private void SelectAll_Click(object sender, RoutedEventArgs e)
    {
        if (Tasks.Count == 0)
        {
            return;
        }

        var selectAll = Tasks.Any(task => !task.IsSelected);
        foreach (var task in Tasks)
        {
            task.IsSelected = selectAll;
        }

        RefreshSummary();
        UpdateHeaderCheckBox();
    }

    private void ClearList_Click(object sender, RoutedEventArgs e)
    {
        if (_isRunning)
        {
            _ = ShowMessageAsync("处理中", "处理过程中暂时不能清空任务。");
            return;
        }

        Tasks.Clear();
        TaskRows.Clear();
        _rowGrids.Clear();
        OverallProgress.Value = 0;
        RefreshSummary();
        UpdateHeaderCheckBox();
    }

    private void OpenOutput_Click(object sender, RoutedEventArgs e)
    {
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

        _ = ShowMessageAsync("提示", "还没有可打开的输出目录。");
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
            await ShowMessageAsync("提示", "请先添加 EPUB 文件。");
            return;
        }

        _settings.LoadAppSettings();
        OutputHintText.Text = OutputHintTextValue;
        _isRunning = true;
        _cancellation = new CancellationTokenSource();
        StartButton.Content = CreateButtonContent("取消处理", "\uE711");
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
                            task.Output = progress.Output!;
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
        StartButton.Content = CreateButtonContent("开始处理", "\uE768");
        if (_cancellation.IsCancellationRequested)
        {
            StatusChanged?.Invoke(this, "任务已取消");
            await ShowMessageAsync("已取消", $"已完成 {success} / {total} 本。");
        }
        else
        {
            StatusChanged?.Invoke(this, "处理完成");
            OverallProgress.Value = 100;
            await ShowMessageAsync("处理完成", $"成功完成 {success} / {total} 本。");
        }

        _cancellation.Dispose();
        _cancellation = null;
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

        RefreshSummary();
        UpdateHeaderCheckBox();
    }

    private void TaskCheckBox_Changed(object sender, RoutedEventArgs e)
    {
        RefreshSummary();
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

    private void TaskRow_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: EpubTask task })
        {
            _ = ShowTaskLogAsync(task);
        }
    }

    private async Task ShowTaskLogAsync(EpubTask task)
    {
        var dialog = new ContentDialog
        {
            Title = $"日志 - {task.Name}",
            Content = BuildLogViewer(task, 360, 520),
            CloseButtonText = "关闭",
            XamlRoot = XamlRoot,
        };
        await dialog.ShowAsync();
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

    private async Task ShowMessageAsync(string title, string message)
    {
        var dialog = new ContentDialog
        {
            Title = title,
            Content = message,
            CloseButtonText = "确定",
            XamlRoot = XamlRoot,
        };
        await dialog.ShowAsync();
    }

    private void RefreshSummary()
    {
        var selected = Tasks.Count(task => task.IsSelected);
        SummaryText.Text = $"{Tasks.Count} 本 EPUB";
        SelectedSummaryText.Text = selected == 0 ? string.Empty : $"已选 {selected}";
    }

    private void UpdateHeaderCheckBox()
    {
        if (HeaderCheckBox is null)
        {
            return;
        }

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
