using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace KindleEpubFixer.WinUI.Models;

public sealed class FontAlias : INotifyPropertyChanged
{
    private string _family;
    private string _fallbacks;

    public FontAlias(string family, string fallbacks)
    {
        _family = family;
        _fallbacks = fallbacks;
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public string Family
    {
        get => _family;
        set => SetField(ref _family, value);
    }

    public string Fallbacks
    {
        get => _fallbacks;
        set => SetField(ref _fallbacks, value);
    }

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return false;
        }

        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        return true;
    }
}
