"""Fill an Opik prompt library from prompts/prompts.py, or refresh that file from Opik.

The app reads its prompts from Opik only. This script is for setup and upkeep:

    uv run python scripts/seed_prompts.py             # show what's missing or different, change nothing
    uv run python scripts/seed_prompts.py --yes       # create the prompts your Opik doesn't have yet
    uv run python scripts/seed_prompts.py --yes --overwrite
                                                      # also push the file's text over prompts that differ
    uv run python scripts/seed_prompts.py --pull      # rewrite prompts/prompts.py from Opik

Without --overwrite, prompts that already exist are never touched, so running this
against a workspace where prompts were edited in Opik can't undo those edits.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from joblyst.config import get_settings
from joblyst.tracing import configure_opik

PROMPTS_FILE = Path(__file__).resolve().parent.parent / "prompts" / "prompts.py"


def _load_file() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("seed_prompts_file", PROMPTS_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PROMPTS


def _client():
    if not configure_opik():
        sys.exit("Opik is not configured. Set OPIK_API_KEY (and OPIK_WORKSPACE if needed) in .env.")
    import opik

    return opik.Opik()


def _in_opik(client, name: str) -> str | None:
    """The latest text of a prompt in Opik, or None if it doesn't exist."""
    try:
        prompt = client.get_prompt(name=name, project_name=get_settings().opik_project_name, no_cache=True)
    except Exception:  # noqa: BLE001 — the SDK raises different errors for "not found"
        return None
    return prompt.prompt if prompt else None


def push(apply: bool, overwrite: bool) -> int:
    client = _client()
    project = get_settings().opik_project_name
    to_push = []
    print(f"Opik project: {project}\n")
    for name, text in _load_file().items():
        current = _in_opik(client, name)
        if current is None:
            status, push_it = "missing  -> will create", True
        elif current == text:
            status, push_it = "same     -> nothing to do", False
        elif overwrite:
            status, push_it = "differs  -> will push as a new version", True
        else:
            status, push_it = "differs  -> kept (Opik's version wins; --overwrite to replace)", False
        print(f"  {name:22} {status}")
        if push_it:
            to_push.append((name, text))

    if not to_push:
        print("\nNothing to push.")
        return 0
    if not apply:
        print(f"\n{len(to_push)} prompt(s) would be pushed. Re-run with --yes to do it.")
        return 0
    for name, text in to_push:
        client.create_prompt(
            name=name, prompt=text, project_name=project, change_description="Seeded from prompts/prompts.py"
        )
    print(f"\nPushed {len(to_push)} prompt(s).")
    return 0


def _literal(text: str) -> str:
    """A readable triple-quoted block when that's exact, a plain repr otherwise."""
    if '"""' in text or "\\" in text or text.endswith('"'):
        return repr(text)
    return f'"""{text}"""'


def pull() -> int:
    """Rewrite prompts/prompts.py with the latest text from Opik, keeping its header."""
    client = _client()
    source = PROMPTS_FILE.read_text()
    header = source[: source.index("# fmt: off")]
    names = list(_load_file())
    lines = [header + "# fmt: off\n"]
    constants = {}
    for name in names:
        text = _in_opik(client, name)
        if text is None:
            sys.exit(f"Prompt {name!r} is in prompts.py but not in Opik; nothing written.")
        constant = name.upper()
        constants[name] = constant
        lines.append(f"{constant} = {_literal(text)}\n")
    lines.append("# Opik prompt name -> text. scripts/seed_prompts.py pushes exactly this.")
    lines.append("PROMPTS = {")
    lines += [f'    "{name}": {constant},' for name, constant in constants.items()]
    lines.append("}")
    PROMPTS_FILE.write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(names)} prompts from Opik to {PROMPTS_FILE.relative_to(Path.cwd())}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="actually push (otherwise only show the plan)")
    parser.add_argument("--overwrite", action="store_true", help="also replace prompts whose text differs")
    parser.add_argument("--pull", action="store_true", help="rewrite prompts/prompts.py from Opik")
    args = parser.parse_args()
    return pull() if args.pull else push(args.yes, args.overwrite)


if __name__ == "__main__":
    sys.exit(main())
