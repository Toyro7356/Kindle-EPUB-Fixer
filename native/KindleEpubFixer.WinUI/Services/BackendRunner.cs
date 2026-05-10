using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace KindleEpubFixer.WinUI.Services;

public sealed record BackendProgress(string Status, int Progress, string? Output);

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

    public async Task<string> BuildEsjzoneAsync(
        string bookUrl,
        string? outputDirectory,
        string? cookie,
        int? maxChapters,
        Action<string> onLog,
        Action<BackendProgress> onProgress,
        CancellationToken cancellationToken)
    {
        string? cookieFile = null;
        try
        {
            if (!string.IsNullOrWhiteSpace(cookie))
            {
                cookieFile = Path.Combine(Path.GetTempPath(), $"kindle-epub-fixer-esjzone-{Guid.NewGuid():N}.cookie.txt");
                await File.WriteAllTextAsync(cookieFile, CleanCookieHeader(cookie), Utf8NoBom, cancellationToken);
            }

            var psi = CreateEsjzoneStartInfo(bookUrl, outputDirectory, cookieFile, maxChapters);
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
        CancellationToken cancellationToken)
    {
        using var process = new Process { StartInfo = psi, EnableRaisingEvents = true };

        process.Start();
        var outputPath = string.Empty;

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
                    case "error":
                        throw new InvalidOperationException(root.GetProperty("message").GetString());
                }
            }
            catch (JsonException)
            {
                onLog(line);
            }
        }

        var error = await process.StandardError.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(error) ? $"Backend exited with code {process.ExitCode}" : error.Trim());
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

    private static ProcessStartInfo CreateEsjzoneStartInfo(
        string bookUrl,
        string? outputDirectory,
        string? cookieFile,
        int? maxChapters)
    {
        var psi = CreateBaseStartInfo();
        psi.ArgumentList.Add("--esjzone-url");
        psi.ArgumentList.Add(bookUrl);
        if (!string.IsNullOrWhiteSpace(outputDirectory))
        {
            psi.ArgumentList.Add("--output-dir");
            psi.ArgumentList.Add(outputDirectory);
        }
        if (!string.IsNullOrWhiteSpace(cookieFile))
        {
            psi.ArgumentList.Add("--esjzone-cookie-file");
            psi.ArgumentList.Add(cookieFile);
        }
        if (maxChapters is > 0)
        {
            psi.ArgumentList.Add("--max-chapters");
            psi.ArgumentList.Add(maxChapters.Value.ToString());
        }

        return psi;
    }
}
