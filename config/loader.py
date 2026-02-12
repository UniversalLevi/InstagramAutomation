"""
Load default config and per-account config (YAML).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

# Default to project root
CONFIG_ROOT = Path(__file__).resolve().parent
ACCOUNTS_DIR = CONFIG_ROOT / "accounts"
DEFAULTS_PATH = CONFIG_ROOT / "defaults.yaml"

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not yaml:
        raise RuntimeError("PyYAML is required for config. Install with: pip install PyYAML")
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_defaults() -> Dict[str, Any]:
    return _load_yaml(DEFAULTS_PATH)


def get_account_config(account_id: str) -> Dict[str, Any]:
    """Load account config. Looks for accounts/<account_id>.yaml or accounts/example.yaml."""
    candidates = [
        ACCOUNTS_DIR / f"{account_id}.yaml",
        ACCOUNTS_DIR / f"{account_id}.yml",
    ]
    for p in candidates:
        if p.exists():
            return _load_yaml(p)
    return _load_yaml(ACCOUNTS_DIR / "example.yaml")


def get_full_config(account_id: str) -> Dict[str, Any]:
    """Merge defaults and account config. Account overrides defaults."""
    defaults = get_defaults()
    account = get_account_config(account_id)

    def merge(base: Dict, override: Dict) -> Dict:
        out = dict(base)
        for k, v in override.items():
            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                out[k] = merge(out[k], v)
            else:
                out[k] = v
        return out

    return merge(defaults, account)


def list_account_configs() -> list[str]:
    """List account_ids that have a config file (excluding example.yaml)."""
    if not ACCOUNTS_DIR.exists():
        return []
    ids_ = []
    for p in ACCOUNTS_DIR.iterdir():
        if p.suffix in (".yaml", ".yml") and p.stem != "example":
            ids_.append(p.stem)
    return sorted(ids_)
