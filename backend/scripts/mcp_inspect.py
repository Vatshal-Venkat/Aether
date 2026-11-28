"""Aether's MCP inspector: connect to an MCP server, see its tools, call them.

Run from backend/:
  python -m scripts.mcp_inspect                                   list tools of our terminology server (in-process)
  python -m scripts.mcp_inspect --url http://127.0.0.1:8001/mcp   ... of any MCP server over HTTP
  python -m scripts.mcp_inspect call search_conditions '{"term": "heart attack"}'
  python -m scripts.mcp_inspect shell                             type "list", "call <tool> <json>", "quit"

(The official graphical one: npx @modelcontextprotocol/inspector, then connect to http://127.0.0.1:8001/mcp.)
"""

import argparse
import asyncio
import json
import shlex
import sys
import time

from mcp import Client


async def list_tools(client: Client) -> None:
    if info := client.server_info:
        print(f"server: {info.name} {info.version or ''}".rstrip())
    for tool in (await client.list_tools()).tools:
        props = (tool.input_schema or {}).get("properties", {})
        required = set((tool.input_schema or {}).get("required", []))
        args = ", ".join(f"{n}{'' if n in required else '?'}: {p.get('type', 'any')}" for n, p in props.items())
        print(f"\n  {tool.name}({args})\n    {(tool.description or '').strip()}")


async def call(client: Client, name: str, raw_args: str) -> None:
    args = json.loads(raw_args or "{}")
    start = time.perf_counter()
    result = await client.call_tool(name, args)
    took = (time.perf_counter() - start) * 1000
    print(f"{'ERROR' if result.is_error else 'ok'} in {took:.0f} ms")
    if result.structured_content is not None:
        print(json.dumps(result.structured_content, indent=2, ensure_ascii=False))
    else:
        for block in result.content:
            print(getattr(block, "text", block))


async def shell(client: Client) -> None:
    print('commands: list | call <tool> <json args> | quit')
    while True:
        try:
            line = input("mcp> ").strip()
        except EOFError:
            return
        if line in ("quit", "exit"):
            return
        try:
            if line == "list":
                await list_tools(client)
            elif line.startswith("call "):
                parts = shlex.split(line[5:]) if '"' not in line else line[5:].split(" ", 1)
                await call(client, parts[0], parts[1] if len(parts) > 1 else "{}")
            elif line:
                print("unknown command")
        except Exception as exc:  # noqa: BLE001 — keep the shell alive
            print(f"error: {exc}")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="MCP server URL (default: Aether's terminology server, in-process)")
    parser.add_argument("command", nargs="?", default="list", choices=["list", "call", "shell"])
    parser.add_argument("tool", nargs="?")
    parser.add_argument("args", nargs="?", default="{}", help="tool arguments as JSON")
    a = parser.parse_args(argv)
    if a.url:
        target = a.url
    else:
        from app.terminology.server import mcp
        target = mcp
    async with Client(target) as client:
        if a.command == "call":
            if not a.tool:
                parser.error("call needs a tool name")
            await call(client, a.tool, a.args)
        elif a.command == "shell":
            await shell(client)
        else:
            await list_tools(client)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
