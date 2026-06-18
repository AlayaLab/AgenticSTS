using System.Linq;
using System.Net;
using System.Threading;
using MegaCrit.Sts2.Core.Logging;

namespace STS2AIAgent.Server;

public sealed class HttpServer
{
    // .NET HttpListener does Host-header-aware prefix matching, so a request
    // hitting Host: localhost:8128 won't match a prefix that names 127.0.0.1
    // (and vice versa) — it'd serve the framework's default 404 stub instead
    // of routing to Router.HandleAsync. Bind both forms so callers using the
    // conventional `http://localhost:8128/` Python default and
    // direct-IP probes both reach the mod. Cross-platform safe; doesn't
    // require Windows URL ACL registration like the `+` wildcard does.
    private static readonly string[] DefaultHosts = { "127.0.0.1", "localhost" };
    // 8128 picked because 8080 collides with Clash for Windows / common HTTP
    // proxy admin panels and dev servers. Auto-port flow (--api-port=auto in
    // scripts/run_agent.py) sets STS2_API_PORT and bypasses this default.
    private const int DefaultPort = 8128;
    private const string LogPrefix = "[STS2AIAgent.HttpServer]";
    private const int StartRetryCount = 20;
    private static readonly TimeSpan StartRetryDelay = TimeSpan.FromMilliseconds(250);

    private static readonly Lazy<HttpServer> LazyInstance = new(() => new HttpServer());

    private readonly object _gate = new();
    private HttpListener? _listener;
    private CancellationTokenSource? _cts;
    private Task? _listenLoopTask;

    public static HttpServer Instance => LazyInstance.Value;

    private HttpServer()
    {
    }

    public void Start()
    {
        lock (_gate)
        {
            if (_listener != null)
            {
                Log.Info($"{LogPrefix} Already started");
                return;
            }

            var prefixes = ResolvePrefixes();
            _listener = StartListenerWithRetry(prefixes);

            _cts = new CancellationTokenSource();
            _listenLoopTask = Task.Run(() => ListenLoopAsync(_listener, _cts.Token));
            Log.Info($"{LogPrefix} Listening on {string.Join(", ", prefixes)}");
        }
    }

    public void Stop()
    {
        HttpListener? listener;
        CancellationTokenSource? cts;
        Task? listenLoopTask;

        lock (_gate)
        {
            if (_listener == null && _cts == null && _listenLoopTask == null)
            {
                return;
            }

            listener = _listener;
            cts = _cts;
            listenLoopTask = _listenLoopTask;
            _listener = null;
            _cts = null;
            _listenLoopTask = null;
        }

        try
        {
            cts?.Cancel();
        }
        catch (Exception ex)
        {
            Log.Warn($"{LogPrefix} Failed to cancel listener token: {ex}");
        }

        try
        {
            if (listener?.IsListening == true)
            {
                listener.Stop();
            }
        }
        catch (Exception ex) when (ex is HttpListenerException or ObjectDisposedException)
        {
            Log.Info($"{LogPrefix} Listener stop completed with shutdown exception: {ex.Message}");
        }

        try
        {
            listener?.Close();
        }
        catch (Exception ex) when (ex is HttpListenerException or ObjectDisposedException)
        {
            Log.Info($"{LogPrefix} Listener close completed with shutdown exception: {ex.Message}");
        }

        try
        {
            listenLoopTask?.Wait(TimeSpan.FromSeconds(2));
        }
        catch (AggregateException ex) when (ex.InnerExceptions.All(inner => inner is OperationCanceledException or HttpListenerException or ObjectDisposedException))
        {
            Log.Info($"{LogPrefix} Listener loop stopped during shutdown.");
        }
        finally
        {
            cts?.Dispose();
        }

        Log.Info($"{LogPrefix} Stopped");
    }

    private static async Task ListenLoopAsync(HttpListener listener, CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            HttpListenerContext? context = null;

            try
            {
                context = await listener.GetContextAsync();
                _ = Task.Run(() => Router.HandleAsync(context, cancellationToken), cancellationToken);
            }
            catch (HttpListenerException) when (cancellationToken.IsCancellationRequested || !listener.IsListening)
            {
                break;
            }
            catch (ObjectDisposedException) when (cancellationToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                Log.Error($"{LogPrefix} Listener loop failed: {ex}");

                if (context != null)
                {
                    await Router.WriteErrorAsync(context.Response, 500, "listener_error", "HTTP listener failed.");
                }
            }
        }
    }

    private static HttpListener StartListenerWithRetry(string[] prefixes)
    {
        for (var attempt = 1; ; attempt++)
        {
            var listener = new HttpListener();
            foreach (var prefix in prefixes)
            {
                listener.Prefixes.Add(prefix);
            }

            try
            {
                listener.Start();
                return listener;
            }
            catch (HttpListenerException ex) when (IsPrefixConflict(ex) && attempt < StartRetryCount)
            {
                listener.Close();
                Log.Warn($"{LogPrefix} Prefix still busy, retrying start ({attempt}/{StartRetryCount - 1})...");
                Thread.Sleep(StartRetryDelay);
            }
        }
    }

    private static string[] ResolvePrefixes()
    {
        var port = DefaultPort;
        var rawPort = Environment.GetEnvironmentVariable("STS2_API_PORT");
        if (!string.IsNullOrWhiteSpace(rawPort) &&
            int.TryParse(rawPort.Trim(), out var parsed) &&
            parsed is > 0 and <= 65535)
        {
            port = parsed;
        }

        return DefaultHosts.Select(h => $"http://{h}:{port}/").ToArray();
    }

    private static bool IsPrefixConflict(HttpListenerException ex)
    {
        return ex.ErrorCode == 183 ||
            ex.NativeErrorCode == 183 ||
            ex.Message.Contains("conflicts with an existing registration", StringComparison.OrdinalIgnoreCase);
    }
}
