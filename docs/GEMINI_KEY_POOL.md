# Gemini Multi-Key Pool

MiniCut supports up to **100 Gemini API keys** in one local pool.

## Why this exists

The V42 workflow should not lose progress when one free-tier key hits quota, rate limits or a transient provider error. Project/timeline state stays local and durable; the key pool only decides which Gemini credential is tried next.

## Import

Use **Import Gemini Keys** in the AI Agent panel.

The import file is plain text:

```
AIza...key1
AIza...key2
AIza...key3
```

One key per line is recommended. Comma- or semicolon-separated values are also accepted. Duplicate keys are ignored. The hard maximum is 100.

## Storage and privacy

Keys are **not** written into `.mcutv42.json` project files, checkpoints, GitHub, MCP state or AI plans.

They are stored in a local user-profile file:

- Windows: `%LOCALAPPDATA%/MiniCutV42/gemini_keys.json`
- other platforms: `~/.minicut-v42/gemini_keys.json`

`MINICUT_GEMINI_KEY_STORE` may override that path. `MINICUT_GEMINI_KEYS` may inject keys from the environment.

The local key-store file contains the real secrets because the provider needs them for requests. MiniCut attempts restrictive file permissions where the OS supports them. This store is local-only, not encrypted by MiniCut.

## Failover behavior

The pool rotates ready keys round-robin.

- **429**: key enters exponential cooldown, another ready key is used.
- **5xx**: shorter exponential cooldown, then fail over.
- **network/transient error**: short cooldown, then fail over.
- **401/403**: key is marked disabled until manually reloaded/re-enabled.
- **400**: treated as a request/schema problem, not as proof that the key is bad.

Provider `Retry-After` values can override the automatic cooldown.

## Secret safety

Public summaries contain only:

- total / ready / cooldown / disabled counts;
- internal key fingerprints;
- masked tails when local UI/debug code explicitly asks for per-key public state.

Full API keys are never exposed through the MiniCut bridge. Error strings are scrubbed for Gemini-key-looking values before being retained.

## Next layer

The next milestone will implement the Gemini request client over evidence packets. It will:

1. acquire a ready key;
2. send only bounded evidence batches, not the whole film;
3. validate structured JSON responses;
4. classify provider failures;
5. report success/failure to this key pool;
6. fail over automatically without losing V42/timeline progress.
