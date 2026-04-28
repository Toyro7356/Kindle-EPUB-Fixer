using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace KindleEpubFixer.WinUI.Models;

public sealed class EpubTask : INotifyPropertyChanged
{
    private string _status = "等待";
    private int _progress;
    private string _output = string.Empty;
    private bool _isSelected;

    public EpubTask(string id, string filePath)
    {
        Id = id;
        FilePath = filePath;
        Name = Path.GetFileName(filePath);
        Folder = Path.GetDirectoryName(filePath) ?? string.Empty;
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public string Id { get; }

    public string FilePath { get; }

    public string Name { get; }

    public string Folder { get; }

    public ObservableCollection<string> Logs { get; } = new();

    public bool IsSelected
    {
        get => _isSelected;
        set => SetField(ref _isSelected, value);
    }

    public string Status
    {
        get => _status;
        set
        {
            if (SetField(ref _status, value))
            {
                OnPropertyChanged(nameof(StatusWithProgress));
            }
        }
    }

    public int Progress
    {
        get => _progress;
        set
        {
            if (SetField(ref _progress, value))
            {
                OnPropertyChanged(nameof(StatusWithProgress));
            }
        }
    }

    public string Output
    {
        get => _output;
        set
        {
            if (SetField(ref _output, value))
            {
                OnPropertyChanged(nameof(OutputName));
            }
        }
    }

    public string OutputName => string.IsNullOrWhiteSpace(Output) ? string.Empty : Path.GetFileName(Output);

    public string StatusWithProgress => $"{Status} {Progress}%";

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return false;
        }

        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
