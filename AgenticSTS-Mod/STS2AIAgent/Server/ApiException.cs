namespace STS2AIAgent.Server;

internal sealed class ApiException : Exception
{
    public ApiException(int statusCode, string code, string message, object? details = null, bool retryable = false)
        : base(message)
    {
        StatusCode = statusCode;
        Code = code;
        Details = details;
        Retryable = retryable;
    }

    public int StatusCode { get; }

    public string Code { get; }

    public object? Details { get; }

    public bool Retryable { get; }
}
