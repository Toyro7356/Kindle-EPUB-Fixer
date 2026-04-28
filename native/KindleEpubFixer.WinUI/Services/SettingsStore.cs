using System.Text.Json;
using KindleEpubFixer.WinUI.Models;

namespace KindleEpubFixer.WinUI.Services;

public sealed class SettingsStore
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public string DefaultOutputDirectory { get; set; } = string.Empty;

    public List<FontAlias> LoadAliases()
    {
        var aliases = new List<FontAlias>();
        if (File.Exists(AppPaths.FontSettingsPath))
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(AppPaths.FontSettingsPath));
            if (doc.RootElement.TryGetProperty("family_aliases", out var familyAliases))
            {
                foreach (var item in familyAliases.EnumerateObject().OrderBy(item => item.Name))
                {
                    var value = item.Value.ValueKind == JsonValueKind.Array
                        ? string.Join(", ", item.Value.EnumerateArray().Select(entry => entry.GetString()).Where(entry => !string.IsNullOrWhiteSpace(entry)))
                        : item.Value.GetString() ?? string.Empty;
                    aliases.Add(new FontAlias(item.Name, value));
                }
            }
        }

        AddDefaultAlias(aliases, "仿宋", "Zhuque Fangsong (technical preview), 朱雀仿宋（预览测试版）");
        AddDefaultAlias(aliases, "宋体", "serif, STSong, Songti SC");
        AddDefaultAlias(aliases, "黑体", "sans-serif, Microsoft YaHei, SimHei");
        AddDefaultAlias(aliases, "楷体", "STKai, KaiTi, serif");
        AddDefaultAlias(aliases, "幼圆", "STYuan, YouYuan, sans-serif");
        return aliases;
    }

    public void LoadAppSettings()
    {
        if (!File.Exists(AppPaths.AppSettingsPath))
        {
            return;
        }

        using var doc = JsonDocument.Parse(File.ReadAllText(AppPaths.AppSettingsPath));
        if (doc.RootElement.TryGetProperty("default_output_dir", out var output))
        {
            DefaultOutputDirectory = output.GetString() ?? string.Empty;
        }
    }

    public void SaveAppSettings()
    {
        var payload = new Dictionary<string, object?>
        {
            ["default_output_dir"] = DefaultOutputDirectory,
        };
        File.WriteAllText(AppPaths.AppSettingsPath, JsonSerializer.Serialize(payload, JsonOptions));
    }

    public void SaveAliases(IEnumerable<FontAlias> aliases)
    {
        var familyAliases = aliases
            .Where(alias => !string.IsNullOrWhiteSpace(alias.Family) && !string.IsNullOrWhiteSpace(alias.Fallbacks))
            .ToDictionary(
                alias => alias.Family,
                alias => alias.Fallbacks.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));

        var payload = new Dictionary<string, object>
        {
            ["family_aliases"] = familyAliases,
        };
        File.WriteAllText(AppPaths.FontSettingsPath, JsonSerializer.Serialize(payload, JsonOptions));
    }

    private static void AddDefaultAlias(List<FontAlias> aliases, string family, string fallbacks)
    {
        if (aliases.Any(alias => string.Equals(alias.Family, family, StringComparison.OrdinalIgnoreCase)))
        {
            return;
        }

        aliases.Add(new FontAlias(family, fallbacks));
    }
}
