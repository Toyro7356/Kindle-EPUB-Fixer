using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using KindleEpubFixer.WinUI.Models;
using Path = System.IO.Path;

namespace KindleEpubFixer.WinUI.ViewModels;

public sealed class HomePageViewModel : INotifyPropertyChanged
{
    private int _taskSeq;

    public event PropertyChangedEventHandler? PropertyChanged;

    public ObservableCollection<EpubTask> Tasks { get; } = new();

    public string SummaryText => $"{Tasks.Count} 本 EPUB";

    public string SelectedSummaryText
    {
        get
        {
            var selected = Tasks.Count(task => task.IsSelected);
            return selected == 0 ? string.Empty : $"已选 {selected}";
        }
    }

    public bool AddFile(string path)
    {
        if (!path.EndsWith(".epub", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        var resolved = Path.GetFullPath(path);
        if (Tasks.Any(task => string.Equals(task.FilePath, resolved, StringComparison.OrdinalIgnoreCase)))
        {
            return false;
        }

        var task = new EpubTask($"task-{++_taskSeq}", resolved);
        task.Logs.Add($"已添加: {resolved}");
        Tasks.Add(task);
        RefreshSummary();
        return true;
    }

    public void ToggleAll()
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
    }

    public void RemoveSelected()
    {
        foreach (var task in Tasks.Where(task => task.IsSelected).ToList())
        {
            Tasks.Remove(task);
        }

        RefreshSummary();
    }

    public void Clear()
    {
        Tasks.Clear();
        RefreshSummary();
    }

    public void RefreshSummary()
    {
        OnPropertyChanged(nameof(SummaryText));
        OnPropertyChanged(nameof(SelectedSummaryText));
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
