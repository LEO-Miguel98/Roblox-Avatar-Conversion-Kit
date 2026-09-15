using System;
using System.IO;
using System.Text;
using System.Windows.Forms;
using PEPlugin;
using PEPlugin.Pmx;

public class RackPmxBridge : PEPluginClass
{
    private Timer timer;
    private IPERunArgs runArgs;
    private DateTime deadlineUtc;

    public RackPmxBridge() : base()
    {
        m_option = new PEPluginOption(true, true, "RACK PMX Bridge");
    }

    public override void Run(IPERunArgs args)
    {
        base.Run(args);
        try
        {
            if (!args.IsBootup)
            {
                ValidateAndReport(args);
                return;
            }

            runArgs = args;
            int seconds = 30;
            int parsed;
            if (Int32.TryParse(Environment.GetEnvironmentVariable("RACK_PMX_TIMEOUT"), out parsed))
                seconds = Math.Max(5, parsed);
            deadlineUtc = DateTime.UtcNow.AddSeconds(seconds);

            timer = new Timer();
            timer.Interval = 250;
            timer.Tick += OnTick;
            timer.Start();
        }
        catch (Exception ex)
        {
            WriteFailure("bridge-start", ex);
        }
    }

    private void OnTick(object sender, EventArgs e)
    {
        try
        {
            string current = runArgs.Host.Connector.Pmx.CurrentPath;
            string target = Environment.GetEnvironmentVariable("RACK_PMX_TARGET") ?? "";
            bool hasModel = !String.IsNullOrEmpty(current);
            bool targetMatches = String.IsNullOrEmpty(target) || SamePath(current, target);

            if (hasModel && targetMatches)
            {
                timer.Stop();
                ValidateAndReport(runArgs);
                return;
            }
            if (DateTime.UtcNow >= deadlineUtc)
            {
                timer.Stop();
                throw new TimeoutException("PMXEditor started, but the requested PMX did not become the current model in time.");
            }
        }
        catch (Exception ex)
        {
            if (timer != null) timer.Stop();
            WriteFailure("wait-for-model", ex);
            CloseIfRequested();
        }
    }

    private void ValidateAndReport(IPERunArgs args)
    {
        try
        {
            IPXPmx pmx = args.Host.Connector.Pmx.GetCurrentState();
            if (pmx == null)
                throw new InvalidOperationException("PMXEditor returned no current PMX state.");

            string current = args.Host.Connector.Pmx.CurrentPath ?? pmx.FilePath ?? "";
            string target = Environment.GetEnvironmentVariable("RACK_PMX_TARGET") ?? "";
            if (!String.IsNullOrEmpty(target) && !SamePath(current, target))
                throw new InvalidOperationException("PMXEditor current model does not match RACK_PMX_TARGET.");

            string resave = Environment.GetEnvironmentVariable("RACK_PMX_RESAVE") ?? "";
            bool resaved = false;
            if (!String.IsNullOrEmpty(resave))
            {
                string dir = Path.GetDirectoryName(resave);
                if (!String.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                pmx.ToFile(resave);
                resaved = File.Exists(resave);
            }

            StringBuilder json = new StringBuilder();
            json.Append("{\n");
            Add(json, "status", "accepted", true);
            Add(json, "current_path", current, true);
            Add(json, "resaved_path", resaved ? resave : "", true);
            Add(json, "vertices", pmx.Vertex.Count, true);
            Add(json, "materials", pmx.Material.Count, true);
            Add(json, "bones", pmx.Bone.Count, true);
            Add(json, "morphs", pmx.Morph.Count, true);
            Add(json, "display_frames", pmx.Node.Count, true);
            Add(json, "rigid_bodies", pmx.Body.Count, true);
            Add(json, "joints", pmx.Joint.Count, true);
            Add(json, "soft_bodies", pmx.SoftBody.Count, false);
            json.Append("\n}\n");
            WriteReport(json.ToString());
        }
        catch (Exception ex)
        {
            WriteFailure("validate", ex);
        }
        finally
        {
            CloseIfRequested();
        }
    }

    private static bool SamePath(string a, string b)
    {
        try
        {
            return String.Equals(Path.GetFullPath(a), Path.GetFullPath(b), StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return String.Equals(a, b, StringComparison.OrdinalIgnoreCase);
        }
    }

    private static string Escape(string value)
    {
        if (value == null) return "";
        return value.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n");
    }

    private static void Add(StringBuilder json, string key, string value, bool comma)
    {
        json.Append("  \"").Append(Escape(key)).Append("\": \"").Append(Escape(value)).Append("\"");
        if (comma) json.Append(",");
        json.Append("\n");
    }

    private static void Add(StringBuilder json, string key, int value, bool comma)
    {
        json.Append("  \"").Append(Escape(key)).Append("\": ").Append(value);
        if (comma) json.Append(",");
        json.Append("\n");
    }

    private static void WriteFailure(string stage, Exception ex)
    {
        StringBuilder json = new StringBuilder();
        json.Append("{\n");
        Add(json, "status", "error", true);
        Add(json, "stage", stage, true);
        Add(json, "error", ex.GetType().FullName + ": " + ex.Message, false);
        json.Append("\n}\n");
        WriteReport(json.ToString());
    }

    private static void WriteReport(string text)
    {
        string report = Environment.GetEnvironmentVariable("RACK_PMX_REPORT") ?? "";
        if (String.IsNullOrEmpty(report)) return;
        string dir = Path.GetDirectoryName(report);
        if (!String.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        File.WriteAllText(report, text, new UTF8Encoding(false));
    }

    private void CloseIfRequested()
    {
        if ((Environment.GetEnvironmentVariable("RACK_PMX_AUTOCLOSE") ?? "0") != "1") return;
        try { runArgs.Host.Connector.Form.Close(); }
        catch { }
    }
}
