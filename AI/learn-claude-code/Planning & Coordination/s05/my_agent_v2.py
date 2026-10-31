#!/usr/bin/env python3
"""my_agent_v2.py - 在 v1(纯 agent loop)之上加 s02~s05 的机制

v1 冻结的原则:循环本体不变,新功能全是"插进插槽的组件"。
    s02  文件工具 + dispatch map(名字→函数) + safe_path   ← 本步
    s03  权限三道门(deny list / 规则 / 用户批准)           ← TODO
    s04  钩子:UserPromptSubmit / PreToolUse / PostToolUse / Stop ← TODO
    s05  todo_write 工具 + 3轮未更新注入提醒                ← TODO
"""

import os
import subprocess
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

WORKDIR = Path.cwd()
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]

SYSTEM = (
    f"You are a coding agent at {WORKDIR}. "
    "Use bash and file tools to solve tasks. Act, don't explain."
)


# -- 工具实现 --

def safe_path(path: str) -> Path:
    """解析成绝对路径并确认没逃出工作区,防目录穿越。"""
    full = (WORKDIR / path).resolve()
    if not full.is_relative_to(WORKDIR):
        raise ValueError(f"path outside workspace: {path}")
    return full


def run_bash(command: str) -> str:
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, errors="replace", timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines) if lines else "(empty file)"
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        p = safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        p = safe_path(path)
        text = p.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: text not found in {path}"   # 不抛异常,让模型自己修正重试
        p.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def run_glob(pattern: str) -> str:
    import glob
    try:
        matches = sorted({
            m for m in glob.glob(pattern, root_dir=WORKDIR, recursive=True)
            if safe_path(m).is_relative_to(WORKDIR)
        })
        shown = matches[:200]
        if len(matches) > 200:
            shown.append("... (more matches omitted)")
        return "\n".join(shown) if shown else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


# -- 权限(s03):三道门,插在 dispatch 之前 --

DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]   # 门1:确定性危险,静默拒
ASK_WORDS = ["rm ", "del ", "chmod", "> /etc/"]                            # 门2:可疑,升级给人类


def check_permission(block) -> str | None:
    """返回拒绝原因文本;None = 放行。"""
    if block.name == "bash":
        command = block.input.get("command", "")
        for pattern in DENY_LIST:                      # 门1:硬拒,不劳烦人类
            if pattern in command:
                return f"Permission denied by deny list: {pattern}"
        if any(w in command for w in ASK_WORDS):       # 门2:可疑 → human in the loop
            print(f"\n[permission] {command}")
            if input("   Allow? [y/N] ").strip().lower() not in ("y", "yes"):
                return "Permission denied by user"
        return None                                    # 门3:其余放行

    if block.name in ("read_file", "write_file", "edit_file"):
        try:
            safe_path(block.input.get("path", ""))     # 结构化参数:精确判定路径边界
        except ValueError as e:
            return f"Permission denied: {e}"
        return None

    return None

# -- 工具注册(dispatch map):名字 → 函数 --

BASE_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}

BASE_TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "limit": {"type": "integer"}},
                      "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string"},
                                     "old_text": {"type": "string"},
                                     "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern; ** matches recursively.",
     "input_schema": {"type": "object",
                      "properties": {"pattern": {"type": "string"}},
                      "required": ["pattern"]}},
]

TOOLS = list(BASE_TOOLS)
TOOL_HANDLERS = dict(BASE_HANDLERS)


# -- 核心循环(v1 冻结,只有执行端换成 dispatch 查询) --

def agent_loop(messages: list):
    while True:
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            return

        results = []
        for block in tool_calls:
            denied = check_permission(block)             # ← s03 循环里新增的一行:先过门
            if denied:
                output = denied                          # 拒绝文本顶替输出,tool_use 依然被回答
            else:
                handler = TOOL_HANDLERS.get(block.name)  # ← dispatch:报名字,查函数
                output = str(handler(**block.input)) if handler else f"Unknown tool: {block.name}"
            print(f"$ {block.name}: {output[:80]}")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    print("my_agent v2: loop + dispatch")
    print("输入问题,回车发送;输入 q 退出。\n")

    history = []
    while True:
        try:
            query = input(">> ")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)
        print()
