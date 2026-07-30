/** ACP agent presets shared by onboarding and settings. */

export type AcpAgentPresetId =
  | 'reins'
  | 'opencode'
  | 'claude'
  | 'codex'
  | 'custom';

export const ACP_AGENT_PRESETS: Record<
  AcpAgentPresetId,
  {
    title: string;
    tagline: string;
    blurb: string;
  }
> = {
  reins: {
    title: 'Reins Agent',
    tagline: 'Built-in Reins connection',
    blurb: 'Connects automatically to your local Reins Agent installation.',
  },

  opencode: {
    title: 'OpenCode',
    tagline: 'Open-source CLI agent',
    blurb: 'Runs as opencode acp.',
  },

  claude: {
    title: 'Claude Code',
    tagline: 'Anthropic coding agent',
    blurb: 'Uses the Claude ACP adapter.',
  },

  codex: {
    title: 'Codex',
    tagline: 'OpenAI coding agent',
    blurb: 'Uses the Codex ACP adapter.',
  },

  custom: {
    title: 'Custom',
    tagline: 'Custom ACP program',
    blurb: 'Runs a user-provided ACP-compatible command.',
  },
};

/*
 * Only Reins is shown to normal Reins Agent Companion users.
 *
 * The other definitions remain temporarily available so existing
 * configuration data can still be parsed during development.
 */
export const ACP_AGENT_PRESET_IDS: AcpAgentPresetId[] = ['reins'];
