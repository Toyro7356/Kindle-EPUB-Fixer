using System.Collections.ObjectModel;
using KindleEpubFixer.WinUI.Models;
using KindleEpubFixer.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace KindleEpubFixer.WinUI.Views;

public sealed partial class SettingsPage : UserControl
{
    private readonly SettingsStore _settings = new();

    public SettingsPage()
    {
        InitializeComponent();
        _settings.LoadAppSettings();
        DefaultOutputBox.Text = _settings.DefaultOutputDirectory;
        foreach (var alias in _settings.LoadAliases())
        {
            Aliases.Add(alias);
        }
    }

    public ObservableCollection<FontAlias> Aliases { get; } = new();

    private async void ChooseOutput_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FolderPicker();
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(App.MainWindowInstance));
        var folder = await picker.PickSingleFolderAsync();
        if (folder is not null)
        {
            DefaultOutputBox.Text = folder.Path;
        }
    }

    private async void AddFonts_Click(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        foreach (var extension in new[] { ".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2" })
        {
            picker.FileTypeFilter.Add(extension);
        }

        InitializeWithWindow.Initialize(picker, WindowNative.GetWindowHandle(App.MainWindowInstance));
        var files = await picker.PickMultipleFilesAsync();
        var copied = 0;
        foreach (var file in files)
        {
            var target = Path.Combine(AppPaths.UserFontsDirectory, Path.GetFileName(file.Path));
            File.Copy(file.Path, target, overwrite: true);
            copied++;
        }

        await ShowMessageAsync("字体已添加", $"已添加 {copied} 个字体到 {AppPaths.UserFontsDirectory}");
    }

    private async void AddAlias_Click(object sender, RoutedEventArgs e)
    {
        var values = await ShowAliasDialogAsync("新增回落");
        if (values is not null)
        {
            Aliases.Add(new FontAlias(values.Value.Family, values.Value.Fallbacks));
        }
    }

    private async void EditAlias_Click(object sender, RoutedEventArgs e)
    {
        if (AliasList.SelectedItem is not FontAlias alias)
        {
            await ShowMessageAsync("提示", "请先选择一条回落设置。");
            return;
        }

        var values = await ShowAliasDialogAsync("编辑回落", alias.Family, alias.Fallbacks);
        if (values is not null)
        {
            alias.Family = values.Value.Family;
            alias.Fallbacks = values.Value.Fallbacks;
        }
    }

    private async void DeleteAlias_Click(object sender, RoutedEventArgs e)
    {
        if (AliasList.SelectedItem is not FontAlias alias)
        {
            await ShowMessageAsync("提示", "请先选择一条回落设置。");
            return;
        }

        Aliases.Remove(alias);
    }

    private async void SaveSettings_Click(object sender, RoutedEventArgs e)
    {
        _settings.DefaultOutputDirectory = DefaultOutputBox.Text.Trim();
        _settings.SaveAppSettings();
        _settings.SaveAliases(Aliases);
        await ShowMessageAsync("设置已保存", "设置已保存，后续处理会使用新的默认值。");
    }

    private async Task<(string Family, string Fallbacks)?> ShowAliasDialogAsync(string title, string family = "", string fallbacks = "")
    {
        var familyBox = new TextBox { Header = "字体名或书内别名", Text = family, PlaceholderText = "例如：仿宋、DK-XiaoBiaoSong、YouYuan" };
        var fallbackBox = new TextBox { Header = "回落链，用英文逗号分隔", Text = fallbacks, PlaceholderText = "例如：Zhuque Fangsong (technical preview), serif" };
        var panel = new StackPanel { Spacing = 12 };
        panel.Children.Add(familyBox);
        panel.Children.Add(fallbackBox);

        var dialog = new ContentDialog
        {
            Title = title,
            Content = panel,
            PrimaryButtonText = "保存",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Primary,
            XamlRoot = XamlRoot,
        };
        var result = await dialog.ShowAsync();
        if (result != ContentDialogResult.Primary)
        {
            return null;
        }

        var newFamily = familyBox.Text.Trim();
        var newFallbacks = fallbackBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(newFamily) || string.IsNullOrWhiteSpace(newFallbacks))
        {
            await ShowMessageAsync("信息不完整", "请填写字体名和回落链。");
            return null;
        }

        return (newFamily, newFallbacks);
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
}
