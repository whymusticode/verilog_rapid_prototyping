"""Agent harnesses: parsing -m, building each CLI's command, sandbox state and
credentials, and recording non-secret model settings.

-m is HARNESS or HARNESS:MODEL. qwen, claude and whale take the prompt on their
command line; codex runs as an app-server and gets the prompt over its protocol
(codex_run.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
HARNESSES = ("qwen", "codex", "claude", "whale")

# Forwarded into an agent sandbox only when set; redacted from dry runs.
SECRET_ENV = ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def check(args: argparse.Namespace) -> str:
    """Validate the model options and return the harness name."""
    harness, separator, model = args.model.partition(":")
    if harness not in HARNESSES or (separator and not model):
        raise ValueError("-m must be qwen, codex, claude, whale, or HARNESS:MODEL")
    if args.qwen_model and (harness != "qwen" or separator):
        raise ValueError("--qwen-model requires -m qwen without a model suffix")
    if args.reasoning_effort is not None and harness not in ("codex", "claude"):
        raise ValueError("--reasoning-effort currently requires the Codex or Claude harness")
    if harness == "claude" and args.reasoning_effort in ("none", "minimal"):
        raise ValueError("Claude Code --effort accepts low, medium, high, xhigh or max")
    return harness


def command(args: argparse.Namespace, harness: str, prompt: str,
            session_id: str | None = None, resume: bool = False) -> list[str]:
    """The agent CLI invocation that runs inside the sandbox.

    Claude runs under ``session_id`` (``resume`` continues it); Codex gets its
    thread over the app-server protocol, and qwen and whale are not resumable.
    """
    if harness == "codex":
        return [args.codex, "app-server"]
    if harness == "claude":
        return claude_command(args, prompt, session_id, resume)
    return {"qwen": qwen_command, "whale": whale_command}[harness](args, prompt)


def qwen_command(args: argparse.Namespace, prompt: str) -> list[str]:
    command = [args.qwen, "-p", prompt, "--approval-mode", "yolo",
               "--output-format", "text",
               "--include-directories", str(args.input.resolve()),
               "--include-directories", str(ROOT)]
    model = args.model.partition(":")[2] or args.qwen_model
    if model:
        command.extend(("--model", model))
    return command


def claude_command(args: argparse.Namespace, prompt: str, session_id: str | None = None,
                   resume: bool = False) -> list[str]:
    # --safe-mode drops the user's CLAUDE.md, skills, plugins, hooks and MCP
    # servers so runs depend only on the prompt; auth and built-in tools remain.
    # The session is persisted under its id so `convert.py --resume` can continue it.
    command = [args.claude, "-p", "--output-format", "stream-json", "--verbose",
               "--include-partial-messages",
               "--dangerously-skip-permissions", "--safe-mode"]
    if session_id:
        command.extend(("--resume" if resume else "--session-id", session_id))
    else:
        command.append("--no-session-persistence")
    model = args.model.partition(":")[2]
    if model:
        command.extend(("--model", model))
    if args.reasoning_effort is not None:
        command.extend(("--effort", args.reasoning_effort))
    return [*command, prompt]


def whale_command(args: argparse.Namespace, prompt: str) -> list[str]:
    command = [args.whale, "exec", "--dangerously-skip-permissions"]
    model = args.model.partition(":")[2]
    if model:
        command.extend(("--model", model))
    return [*command, prompt]


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")).expanduser().resolve()


def whale_home() -> Path:
    return Path(os.environ.get("WHALE_HOME", Path.home() / ".whale")).expanduser().resolve()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def public_settings(value: object) -> object:
    """Keep configuration useful for comparisons without recording credentials."""
    if isinstance(value, dict):
        return {key: public_settings(item) for key, item in value.items()
                if isinstance(key, str) and not re.search(
                    r"key|token|secret|password|credential|authorization|auth", key,
                    re.IGNORECASE)}
    if isinstance(value, list):
        return [public_settings(item) for item in value]
    return value


def public_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if not parsed.hostname:
        return None
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    if port:
        host += f":{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def cli_version(executable: str) -> str | None:
    try:
        result = subprocess.run([executable, "--version"], capture_output=True,
                                text=True, timeout=5, check=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else None


def codex_catalog(executable: str) -> tuple[dict, str]:
    try:
        result = subprocess.run([executable, "debug", "models"], capture_output=True,
                                text=True, timeout=10, check=True)
        catalog = json.loads(result.stdout)
        if isinstance(catalog, dict) and isinstance(catalog.get("models"), list):
            return catalog, "codex debug models"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError):
        pass
    cached = read_json(codex_home() / "models_cache.json")
    return cached, "Codex models_cache.json" if cached else "unavailable"


def settings(args: argparse.Namespace) -> dict:
    """Snapshot non-secret model and harness settings for a batch experiment."""
    harness, _, requested = args.model.partition(":")
    info = {"model": requested or None, "harness": harness}
    if harness == "codex":
        config = read_toml(codex_home() / "config.toml")
        active_config = dict(config)
        profiles = config.get("profiles")
        profile = config.get("profile")
        if isinstance(profiles, dict) and isinstance(profile, str):
            selected_profile = profiles.get(profile)
            if isinstance(selected_profile, dict):
                active_config.update(selected_profile)
        catalog, source = codex_catalog(args.codex)
        models = [item for item in catalog.get("models", [])
                  if isinstance(item, dict) and isinstance(item.get("slug"), str)]
        selected = requested or active_config.get("model")
        if not selected:
            visible = [item for item in models if item.get("visibility") == "list"]
            selected = min(visible, key=lambda item: item.get("priority", 9999)).get("slug") if visible else None
        info["model"] = selected
        info["cli_version"] = cli_version(args.codex)
        info["catalog_source"] = source
        for key in ("model_reasoning_effort", "model_verbosity", "service_tier",
                    "model_provider", "profile"):
            if isinstance(active_config.get(key), (str, int, float, bool)):
                info[f"configured_{key}"] = active_config[key]
        entry = next((item for item in models if item["slug"] == selected), None)
        if entry:
            # These are prompt/onboarding text, not adjustable model settings.
            excluded = {"slug", "base_instructions", "model_messages",
                        "availability_nux"}
            info.update((key, value) for key, value in entry.items()
                        if key not in excluded)
    elif harness == "qwen":
        config = read_json(Path.home() / ".qwen" / "settings.json")
        configured = config.get("model")
        info["model"] = requested or args.qwen_model or (
            configured.get("name") if isinstance(configured, dict) else None)
        info["cli_version"] = cli_version(args.qwen)
        if isinstance(configured, dict):
            info["configured_model_settings"] = public_settings(configured)
    elif harness == "claude":
        config = read_json(claude_home() / "settings.json")
        info["model"] = requested or config.get("model") or os.environ.get("ANTHROPIC_MODEL")
        info["cli_version"] = cli_version(args.claude)
        for key in ("effortLevel", "alwaysThinkingEnabled"):
            if key in config:
                info[f"configured_{key}"] = config[key]
    else:
        config = read_toml(whale_home() / "config.toml")
        info["model"] = requested or config.get("model") or "deepseek-v4-flash"
        info["cli_version"] = cli_version(args.whale)
        for key in ("reasoning_effort", "thinking_enabled"):
            if key in config:
                info[key] = config[key]
        providers = config.get("providers")
        provider = providers.get("deepseek", {}) if isinstance(providers, dict) else {}
        if isinstance(provider, dict):
            for key in ("api", "web_search"):
                if key in provider:
                    info[key] = provider[key]
        if os.environ.get("WHALE_API"):
            info["api"] = os.environ["WHALE_API"]
        endpoint = config.get("api")
        base_url = os.environ.get("DEEPSEEK_BASE_URL") or (
            endpoint.get("base_url") if isinstance(endpoint, dict) else None)
        if url := public_url(base_url):
            info["api_base_url"] = url
    info["requested_reasoning_effort"] = args.reasoning_effort
    info["codex_transport"] = "app-server" if harness == "codex" else None
    info["claude_transport"] = "print stream-json" if harness == "claude" else None
    return info


def complete_models(prefix: str) -> None:
    """Offer the visible models in Codex's /model catalog."""
    if prefix in ("", "qwen"):
        print("qwen")
    if "whale".startswith(prefix):
        print("whale")
    if "claude".startswith(prefix):
        print("claude")
    for alias in ("fable", "opus", "sonnet", "haiku"):
        if f"claude:{alias}".startswith(prefix) and prefix.startswith("claude"):
            print(f"claude:{alias}")
    if not prefix.startswith("codex:") and "codex:".startswith(prefix):
        print("codex:")
    if not prefix.startswith("codex:"):
        return
    try:
        result = subprocess.run(
            [os.environ.get("CODEX", "codex"), "debug", "models"],
            capture_output=True, text=True, timeout=5, check=True)
        catalog = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError):
        try:
            catalog = json.loads((codex_home() / "models_cache.json").read_text())
        except (OSError, ValueError):
            return
    for model in catalog.get("models", []):
        if isinstance(model, dict) and model.get("visibility") == "list":
            slug = model.get("slug")
            if isinstance(slug, str) and f"codex:{slug}".startswith(prefix):
                print(f"codex:{slug}")


def sandbox_binds(harness: str) -> list[str]:
    """bwrap arguments giving one harness its state directory and credentials."""
    home = Path.home()
    wrapped = []
    if harness == "qwen" and (home / ".qwen").exists():
        wrapped.extend(("--bind", str(home / ".qwen"), str(home / ".qwen")))
    if harness == "codex":
        auth = codex_home()
        if not auth.is_dir():
            raise RuntimeError(f"Codex home does not exist: {auth}")
        wrapped.extend(("--bind", str(auth), str(auth)))
        wrapped.extend(("--setenv", "CODEX_HOME", str(auth)))
    if harness == "claude":
        state = claude_home()
        if not state.is_dir():
            raise RuntimeError(f"Claude Code home does not exist: {state}; run claude and log in first")
        wrapped.extend(("--bind", str(state), str(state)))
        if "CLAUDE_CONFIG_DIR" in os.environ:
            wrapped.extend(("--setenv", "CLAUDE_CONFIG_DIR", str(state)))
        elif (home / ".claude.json").is_file():
            # The global config (account, onboarding) lives beside the directory.
            wrapped.extend(("--bind", str(home / ".claude.json"), str(home / ".claude.json")))
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
            if value := os.environ.get(name):
                wrapped.extend(("--setenv", name, value))
    if harness == "whale":
        state = whale_home()
        if not state.is_dir():
            raise RuntimeError(f"Whale home does not exist: {state}; run whale setup first")
        wrapped.extend(("--bind", str(state), str(state)))
        wrapped.extend(("--setenv", "WHALE_HOME", str(state)))
        for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "WHALE_API"):
            if value := os.environ.get(name):
                wrapped.extend(("--setenv", name, value))

    return wrapped
