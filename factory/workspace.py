"""Per-job workspaces and the sandboxed file/shell tools the builder uses."""
from __future__ import annotations

import asyncio
import shlex
import shutil
from pathlib import Path

from agents import FunctionTool, function_tool

from factory.jobs import Job

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"
WORKSPACE = REPO / "workspace"
MAX_OUTPUT = 8192
ALLOWED_COMMANDS = {"rasa", "python", "ls", "cat", "grep", "head", "tail", "wc", "find"}
TEMPLATE_FOR = {"dashboard": "dashboard", "mantle_agent": "mantle_agent"}


def prepare_workspace(job: Job, base: Path = WORKSPACE) -> Path:
    """Copy the job's template into a fresh workspace folder and return it."""
    root = Path(base) / job.id
    shutil.copytree(TEMPLATES / TEMPLATE_FOR[job.kind], root,
                    ignore=shutil.ignore_patterns("__pycache__", "models", "cache", ".env"))
    return root


class WorkspaceTools:
    """File and shell access confined to one folder."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def _resolve(self, path: str) -> Path:
        p = (self.root / path).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError(f"{path!r} is outside the workspace")
        return p

    def list_files(self, path: str = ".") -> list[str]:
        base = self._resolve(path)
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*")
                      if p.is_file() and ".rasa" not in p.parts and "models" not in p.parts
                      and "__pycache__" not in p.parts)

    def read_file(self, path: str) -> str:
        return self._resolve(path).read_text()

    def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {path} ({len(content)} chars)"

    async def run_command(self, cmd: str, timeout_s: int = 120) -> str:
        argv = shlex.split(cmd)
        if not argv or argv[0] not in ALLOWED_COMMANDS:
            return f"Command not allowed. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}."
        proc = await asyncio.create_subprocess_exec(*argv, cwd=self.root, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return f"Command timed out after {timeout_s}s."
        text = out.decode(errors="replace")
        if len(text) > MAX_OUTPUT:
            text = text[:MAX_OUTPUT] + f"\n… [truncated {len(text) - MAX_OUTPUT} chars]"
        return f"exit={proc.returncode}\n{text}"

    def as_function_tools(self, *, read_only: bool = False) -> list[FunctionTool]:
        ws = self

        @function_tool
        def list_files(path: str = ".") -> list[str]:
            """List files in the workspace (relative paths)."""
            return ws.list_files(path)

        @function_tool
        def read_file(path: str) -> str:
            """Read a file from the workspace."""
            return ws.read_file(path)

        @function_tool
        def write_file(path: str, content: str) -> str:
            """Create or overwrite a file in the workspace."""
            return ws.write_file(path, content)

        @function_tool
        async def run_command(cmd: str, timeout_s: int = 120) -> str:
            """Run a command in the workspace (rasa, python, ls, cat, grep, head, tail, wc, find)."""
            return await ws.run_command(cmd, timeout_s)

        return [list_files, read_file] if read_only else [list_files, read_file, write_file, run_command]
