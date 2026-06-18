using System;
using System.IO;
using System.Linq;
using System.Reflection;

var defaultGameDir = @"C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2\data_sts2_windows_x86_64";
var dllPath = args.FirstOrDefault(a => a.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
    ?? Path.Combine(defaultGameDir, "sts2.dll");
var filters = args
    .Where(a => !a.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
    .ToArray();
if (filters.Length == 0)
{
    filters = new[] { "CrystalSphere" };
}

var gameDir = Path.GetDirectoryName(dllPath)
    ?? throw new InvalidOperationException($"Could not resolve directory for {dllPath}");

var runtimeDir = Path.GetDirectoryName(typeof(object).Assembly.Location)!;
var runtimeDlls = Directory.GetFiles(runtimeDir, "*.dll").ToDictionary(Path.GetFileName, p => p);
var gameDlls = Directory.GetFiles(gameDir, "*.dll").ToDictionary(Path.GetFileName, p => p);
var merged = new Dictionary<string, string>(gameDlls);
foreach (var kvp in runtimeDlls)
{
    merged[kvp.Key] = kvp.Value;
}

var resolver = new PathAssemblyResolver(merged.Values);
using var mlc = new MetadataLoadContext(resolver, coreAssemblyName: "System.Runtime");
var asm = mlc.LoadFromAssemblyPath(dllPath);

var flags = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Static;
var matches = asm.GetTypes()
    .Where(t =>
    {
        var haystack = $"{t.FullName}|{t.Name}";
        return filters.Any(filter => haystack.Contains(filter, StringComparison.OrdinalIgnoreCase));
    })
    .OrderBy(t => t.FullName)
    .ToArray();

Console.WriteLine($"DLL: {dllPath}");
Console.WriteLine($"Filters: {string.Join(", ", filters)}");
Console.WriteLine($"Matches: {matches.Length}");

foreach (var type in matches)
{
    Console.WriteLine($"\n=== {type.FullName} ===");
    Console.WriteLine($"  Base: {type.BaseType?.FullName}");

    Console.WriteLine("  --- Fields ---");
    foreach (var f in type.GetFields(flags).Where(f => f.DeclaringType == type))
    {
        var mod = f.IsPublic ? "pub" : "priv";
        var stat = f.IsStatic ? " static" : "";
        Console.WriteLine($"    {mod}{stat} {f.Name} : {f.FieldType.Name}");
    }

    Console.WriteLine("  --- Properties ---");
    foreach (var p in type.GetProperties(flags).Where(p => p.DeclaringType == type))
    {
        Console.WriteLine($"    {p.Name} : {p.PropertyType.Name}");
    }

    Console.WriteLine("  --- Methods (declared) ---");
    foreach (var m in type.GetMethods(flags).Where(m => m.DeclaringType == type).OrderBy(m => m.Name))
    {
        var parms = string.Join(", ", m.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"));
        Console.WriteLine($"    {m.Name}({parms}) : {m.ReturnType.Name}");
    }
}
