import { useEffect, useState } from "react";
import {
  getAgentSetupStatus,
  installAgentSetup,
  type AgentSetupStatusResponse,
} from "../../api/tauri";
import { ACP_AGENT_PRESETS, type AcpAgentPresetId } from "../../lib/agentPresets";
import { useLanguage } from "../../i18n/LanguageContext";

export function AgentSetupPanel({
  preset,
  onStatusChange,
  friendly,
}: {
  preset: AcpAgentPresetId;
  onStatusChange?: (status: AgentSetupStatusResponse | null, loading: boolean) => void;
  /** Shorter, non-technical copy for onboarding */
  friendly?: boolean;
}) {
  const { tr } = useLanguage();
  const [status, setStatus] = useState<AgentSetupStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (preset === "custom") {
      setStatus(null);
      setError("");
      onStatusChange?.(null, false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    onStatusChange?.(null, true);
    getAgentSetupStatus(preset)
      .then((s) => {
        if (!cancelled) {
          setStatus(s);
          onStatusChange?.(s, false);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [preset]);

  const runInstall = async () => {
    setInstalling(true);
    setError("");
    try {
      const s = await installAgentSetup(preset);
      setStatus(s);
      onStatusChange?.(s, false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstalling(false);
    }
  };

  if (preset === "custom") return null;

  const title = ACP_AGENT_PRESETS[preset].title;
  const agent = status?.agent;
  const usingSystem = agent?.install_source === "system";
  const usingManaged = agent?.install_source === "managed";
  const usingNpx = agent?.install_source === "npx";

  return (
    <div className="rounded-2xl border border-slate-200/90 bg-slate-50/80 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-600">
          {friendly
            ? tr('Agent on your system', '本机智能体')
            : tr('Agent CLI', '智能体 CLI')}
        </span>
        {loading && (
          <span className="text-xs text-slate-400">
            {tr('Checking…', '正在检查...')}
          </span>
        )}
      </div>

      {status && !loading && agent && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            <StatusPill
              ok={agent.ready}
              label={
                agent.ready
                  ? tr(`${title} ready`, `${title} 已就绪`)
                  : tr(`${title} needed`, `需要安装 ${title}`)
              }
            />
            {usingSystem && <StatusPill ok label="System PATH" />}
            {usingManaged && <StatusPill ok label="Meuxe fallback" />}
            {usingNpx && <StatusPill ok label="via npx" />}
            <StatusPill ok={status.prerequisites.node_available} label="Node.js" />
            {status.prerequisites.node_version && (
              <span className="text-[11px] text-slate-400">{status.prerequisites.node_version}</span>
            )}
          </div>

          <p className="text-sm text-slate-600 leading-snug">{agent.detail}</p>

          {friendly && !agent.ready && (
            <p className="text-sm text-slate-500 leading-snug">
              {tr(
                'Install the CLI globally now, or tap Finish and Meuxe will run the same global npm install for you.',
                '你可以现在全局安装 CLI，也可以点击“完成”，由 Reins 自动执行相同的 npm 全局安装。',
              )}
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            {!status.prerequisites.node_available && (
              <button
                type="button"
                onClick={() => window.open("https://nodejs.org/en/download", "_blank")}
                className="rounded-xl border border-amber-200 bg-white px-3.5 py-2 text-sm font-semibold text-amber-900 hover:bg-amber-50"
              >
                {tr('Install Node.js', '安装 Node.js')}
              </button>
            )}
            {status.prerequisites.node_available && !agent.ready && (
              <button
                type="button"
                onClick={runInstall}
                disabled={installing}
                className="rounded-xl bg-violet-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
              >
                {installing
                  ? tr('Installing…', '正在安装...')
                  : tr('Install globally (npm)', '全局安装（npm）')}
              </button>
            )}
            {status.prerequisites.node_available && agent.ready && usingSystem && (
              <span className="text-xs font-semibold text-emerald-700">
                {tr('Using your global install', '正在使用全局安装')}
              </span>
            )}
            {status.prerequisites.node_available && agent.ready && !usingSystem && (
              <button
                type="button"
                onClick={runInstall}
                disabled={installing}
                className="rounded-xl border border-violet-200 bg-white px-3.5 py-2 text-sm font-semibold text-violet-800 hover:bg-violet-50 disabled:opacity-50"
              >
                {installing
                  ? tr('Installing…', '正在安装...')
                  : tr('Install globally (npm)', '全局安装（npm）')}
              </button>
            )}
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}

function StatusPill({
  ok,
  label,
  muted,
}: {
  ok: boolean;
  label: string;
  muted?: boolean;
}) {
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
        ok ? "bg-emerald-100 text-emerald-800" : muted ? "bg-slate-200 text-slate-600" : "bg-amber-100 text-amber-900"
      }`}
    >
      {label}
    </span>
  );
}
