using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace KindleEpubFixer.WinUI.Services;

public sealed record BackendProgress(string Status, int Progress, string? Output);
public sealed record MasiroPurchasePlan(int ChapterCount, int TotalCost, int? AccountBalance);

public sealed class BackendRunner
{
    private static readonly Encoding Utf8NoBom = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);

    public async Task<string> ProcessAsync(
        string inputPath,
        string? outputDirectory,
        Action<string> onLog,
        Action<BackendProgress> onProgress,
        CancellationToken cancellationToken)
    {
        var psi = CreateStartInfo(inputPath, outputDirectory);
        return await RunAsync(psi, onLog, onProgress, cancellationToken);
    }

    public async Task<string> BuildNovelAsync(
        string sourceId,
        string bookUrl,
        string? outputDirectory,
        string? cookie,
        string? userAgent,
        bool autoPurchase,
        int? maxPurchaseCost,
        int? maxChapters,
        int? chapterStart,
        int? chapterEnd,
        Action<string> onLog,
        Action<BackendProgress> onProgress,
        CancellationToken cancellationToken)
    {
        string? cookieFile = null;
        try
        {
            if (!string.IsNullOrWhiteSpace(cookie))
            {
                cookieFile = Path.Combine(Path.GetTempPath(), $"kindle-epub-fixer-{sourceId}-{Guid.NewGuid():N}.cookie.txt");
                await File.WriteAllTextAsync(cookieFile, CleanCookieHeader(cookie), Utf8NoBom, cancellationToken);
            }

            var psi = CreateNovelStartInfo(
                sourceId,
                bookUrl,
                outputDirectory,
                cookieFile,
                userAgent,
                autoPurchase,
                maxPurchaseCost,
                maxChapters,
                chapterStart,
                chapterEnd);
            return await RunAsync(psi, onLog, onProgress, cancellationToken);
        }
        finally
        {
            if (!string.IsNullOrWhiteSpace(cookieFile))
            {
                try
                {
                    File.Delete(cookieFile);
                }
                catch
                {
                }
            }
        }
    }

    public async Task<MasiroPurchasePlan> PreviewMasiroPurchaseAsync(
        string bookUrl,
        string? cookie,
        string? userAgent,
        int? maxChapters,
        int? chapterStart,
        int? chapterEnd,
        CancellationToken cancellationToken)
    {
        string? cookieFile = null;
        try
        {
            if (!string.IsNullOrWhiteSpace(cookie))
            {
                cookieFile = Path.Combine(Path.GetTempPath(), $"kindle-epub-fixer-masiro-{Guid.NewGuid():N}.cookie.txt");
                await File.WriteAllTextAsync(cookieFile, CleanCookieHeader(cookie), Utf8NoBom, cancellationToken);
            }

            var psi = CreateMasiroPreviewStartInfo(bookUrl, cookieFile, userAgent, maxChapters, chapterStart, chapterEnd);
            MasiroPurchasePlan? plan = null;
            await RunAsync(
                psi,
                _ => { },
                _ => { },
                cancellationToken,
                purchasePlan => plan = purchasePlan);
            return plan ?? throw new InvalidOperationException("Backend did not return a Masiro purchase preview.");
        }
        finally
        {
            if (!string.IsNullOrWhiteSpace(cookieFile))
            {
                try
                {
                    File.Delete(cookieFile);
                }
                catch
                {
                }
            }
        }
    }

    private static string CleanCookieHeader(string cookie)
    {
        var cleaned = cookie
            .Replace("\ufeff", string.Empty, StringComparison.Ordinal)
            .Replace("\u200b", string.Empty, StringComparison.Ordinal)
            .Replace("\r", string.Empty, StringComparison.Ordinal)
            .Replace("\n", string.Empty, StringComparison.Ordinal)
            .Replace("\t", string.Empty, StringComparison.Ordinal)
            .Trim();

        return string.Join("; ", cleaned
            .Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));
    }

    private static async Task<string> RunAsync(
        ProcessStartInfo psi,
        Action<string> onLog,
        Action<BackendProgress> onProgress,
        CancellationToken cancellationToken,
        Action<MasiroPurchasePlan>? onPurchasePlan = null)
    {
        using var process = new Process { StartInfo = psi, EnableRaisingEvents = true };

        process.Start();
        var outputPath = string.Empty;
        var errorBuilder = new StringBuilder();
        var errorTask = Task.Run(async () =>
        {
            string? errorLine;
            while ((errorLine = await process.StandardError.ReadLineAsync(cancellationToken)) is not null)
            {
                if (errorLine.Length > 0)
                {
                    errorBuilder.AppendLine(errorLine);
                }
            }
        }, CancellationToken.None);

        string? line;
        while ((line = await process.StandardOutput.ReadLineAsync(cancellationToken)) is not null)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            try
            {
                using var doc = JsonDocument.Parse(line);
                var root = doc.RootElement;
                var eventName = root.GetProperty("event").GetString();
                switch (eventName)
                {
                    case "log":
                        onLog(root.GetProperty("message").GetString() ?? string.Empty);
                        break;
                    case "progress":
                        var status = root.TryGetProperty("status", out var statusElement) ? statusElement.GetString() ?? string.Empty : string.Empty;
                        var progress = root.TryGetProperty("progress", out var progressElement) ? progressElement.GetInt32() : 0;
                        var output = root.TryGetProperty("output", out var outputElement) ? outputElement.GetString() : null;
                        if (!string.IsNullOrWhiteSpace(output))
                        {
                            outputPath = output!;
                        }
                        onProgress(new BackendProgress(status, progress, output));
                        break;
                    case "done":
                        outputPath = root.GetProperty("output").GetString() ?? outputPath;
                        break;
                    case "purchase_plan":
                        var chapterCount = root.GetProperty("chapter_count").GetInt32();
                        var totalCost = root.GetProperty("total_cost").GetInt32();
                        int? accountBalance = root.TryGetProperty("account_balance", out var balanceElement)
                            && balanceElement.ValueKind == JsonValueKind.Number
                            ? balanceElement.GetInt32()
                            : null;
                        onPurchasePlan?.Invoke(new MasiroPurchasePlan(chapterCount, totalCost, accountBalance));
                        break;
                    case "error":
                        throw new InvalidOperationException(root.GetProperty("message").GetString());
                }
            }
            catch (JsonException)
            {
                onLog(line);
            }
        }

        await process.WaitForExitAsync(cancellationToken);
        await errorTask;
        var error = errorBuilder.ToString().Trim();
        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(error) ? $"Backend exited with code {process.ExitCode}" : error);
        }

        return outputPath;
    }

    private static ProcessStartInfo CreateBaseStartInfo()
    {
        var backendExe = AppPaths.BackendExecutable;
        ProcessStartInfo psi;
        if (!string.IsNullOrWhiteSpace(backendExe))
        {
            psi = new ProcessStartInfo(backendExe);
        }
        else
        {
            var script = AppPaths.BackendScript ?? throw new FileNotFoundException("Cannot locate main_backend.py or KindleEpubFixer.Backend.exe.");
            psi = new ProcessStartInfo(AppPaths.PythonExecutable);
            psi.ArgumentList.Add(script);
        }

        psi.UseShellExecute = false;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.StandardOutputEncoding = Encoding.UTF8;
        psi.StandardErrorEncoding = Encoding.UTF8;
        psi.CreateNoWindow = true;
        psi.Environment["KINDLE_EPUB_FIXER_FONT_DIRS"] = AppPaths.FontSearchPath;
        return psi;
    }

    private static ProcessStartInfo CreateStartInfo(string inputPath, string? outputDirectory)
    {
        var psi = CreateBaseStartInfo();
        psi.ArgumentList.Add("--input");
        psi.ArgumentList.Add(inputPath);
        if (!string.IsNullOrWhiteSpace(outputDirectory))
        {
            psi.ArgumentList.Add("--output-dir");
            psi.ArgumentList.Add(outputDirectory);
        }

        return psi;
    }

    private static ProcessStartInfo CreateNovelStartInfo(
        string sourceId,
        string bookUrl,
        string? outputDirectory,
        string? cookieFile,
        string? userAgent,
        bool autoPurchase,
        int? maxPurchaseCost,
        int? maxChapters,
        int? chapterStart,
        int? chapterEnd)
    {
        var psi = CreateBaseStartInfo();
        psi.ArgumentList.Add("--novel-source");
        psi.ArgumentList.Add(sourceId);
        psi.ArgumentList.Add("--novel-url");
        psi.ArgumentList.Add(bookUrl);
        if (!string.IsNullOrWhiteSpace(outputDirectory))
        {
            psi.ArgumentList.Add("--output-dir");
            psi.ArgumentList.Add(outputDirectory);
        }
        if (!string.IsNullOrWhiteSpace(cookieFile))
        {
            psi.ArgumentList.Add("--novel-cookie-file");
            psi.ArgumentList.Add(cookieFile);
        }
        if (!string.IsNullOrWhiteSpace(userAgent))
        {
            psi.ArgumentList.Add("--novel-user-agent");
            psi.ArgumentList.Add(userAgent);
        }
        if (autoPurchase)
        {
            psi.ArgumentList.Add("--novel-auto-purchase");
            if (maxPurchaseCost is not null)
            {
                psi.ArgumentList.Add("--novel-max-purchase-cost");
                psi.ArgumentList.Add(maxPurchaseCost.Value.ToString());
            }
        }
        if (maxChapters is > 0)
        {
            psi.ArgumentList.Add("--max-chapters");
            psi.ArgumentList.Add(maxChapters.Value.ToString());
        }
        if (chapterStart is > 0)
        {
            psi.ArgumentList.Add("--chapter-start");
            psi.ArgumentList.Add(chapterStart.Value.ToString());
        }
        if (chapterEnd is > 0)
        {
            psi.ArgumentList.Add("--chapter-end");
            psi.ArgumentList.Add(chapterEnd.Value.ToString());
        }

        return psi;
    }

    private static ProcessStartInfo CreateMasiroPreviewStartInfo(
        string bookUrl,
        string? cookieFile,
        string? userAgent,
        int? maxChapters,
        int? chapterStart,
        int? chapterEnd)
    {
        var psi = CreateBaseStartInfo();
        psi.ArgumentList.Add("--masiro-url");
        psi.ArgumentList.Add(bookUrl);
        psi.ArgumentList.Add("--masiro-preview");
        if (!string.IsNullOrWhiteSpace(cookieFile))
        {
            psi.ArgumentList.Add("--masiro-cookie-file");
            psi.ArgumentList.Add(cookieFile);
        }
        if (!string.IsNullOrWhiteSpace(userAgent))
        {
            psi.ArgumentList.Add("--masiro-user-agent");
            psi.ArgumentList.Add(userAgent);
        }
        if (maxChapters is > 0)
        {
            psi.ArgumentList.Add("--max-chapters");
            psi.ArgumentList.Add(maxChapters.Value.ToString());
        }
        if (chapterStart is > 0)
        {
            psi.ArgumentList.Add("--chapter-start");
            psi.ArgumentList.Add(chapterStart.Value.ToString());
        }
        if (chapterEnd is > 0)
        {
            psi.ArgumentList.Add("--chapter-end");
            psi.ArgumentList.Add(chapterEnd.Value.ToString());
        }
        return psi;
    }
}
