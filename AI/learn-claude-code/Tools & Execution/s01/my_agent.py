#!/usr/bin/env python3
"""my_agent.py - 从零手写的最小 Agent Loop(练习作品)

设计(来自问题 1 的口述,已修正):
    while True:
        response = LLM(model, system, messages, tools)
        追加 assistant 回复到 messages            ← 回答C: 第一次追加(必做)
        if 回复里没有 tool_use 块: return          ← 回答B: 停止条件
        执行工具, tool_result 作为 user 消息追加   ← 回答C: 第二次追加
"""

import os
import subprocess

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]

SYSTEM = "You are a coding agent. Use bash to solve tasks. Act, don't explain."

TOOLS = [
    {
        "name": "bash",                          # 模型调工具时引用的名字
        "description": "Run a shell command.",   # 给模型看的说明书:何时用我
        "input_schema": {                        # 参数描述,JSON Schema 格式
            "type": "object",                    # 顶层是一个参数包
            "properties": {
                "command": {"type": "string"}    # 包里有一个字符串参数 command
            },
            "required": ["command"],             # 必填 = 在这里点名
        },
    }
]

def run_bash(command: str) -> str:
    """执行 shell 命令。永不抛异常:所有失败都变成模型可读的文本。"""
    try:
        r = subprocess.run(
            command,
            shell=True,           # Windows 上由 cmd.exe 解释
            capture_output=True,  # 输出回到我们手里,而不是打到控制台
            text=True,
            errors="replace",     # 乱码/二进制不至于让程序崩
            timeout=120,          # 防卡死,超时抛 TimeoutExpired
        )
        out = (r.stdout + r.stderr).strip()   # 两个流合并:报错信息对模型同样有价值
        return out[:50000] if out else "(no output)"   # 截断护上下文;空串会被 API 拒收
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
def agent_loop(messages: list):
    while True:
        # 1. 请求:全部配置 + 全部历史,每次全量发送(API 无状态)
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )

        # 2. 先收货入库:assistant 回复必进 history(漏了它 = API 报错 + 模型失忆)
        messages.append({"role": "assistant", "content": response.content})

        # 3. 验货:挑出所有 tool_use 块 —— 这也是唯一的停止条件
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            return                    # 模型不再要工具 = 它决定说完了

        # 4. 非空:逐个执行,打包 tool_result
        results = []
        for block in tool_calls:
            print(f"$ {block.input['command']}")          # 回显命令
            output = run_bash(block.input["command"])
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,   # 认亲凭据:抄自 tool_use 块的 id
                "content": output,
            })

        # 5. 第二次追加:user 外衣;while True 自然进入下一轮 = "再次请求"
        messages.append({"role": "user", "content": results})
if __name__ == "__main__":
    print("my_agent: 从零手写的 Agent Loop")
    print("输入问题,回车发送;输入 q 退出。\n")

    history = []
    while True:
        try:
            query = input(">> ")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        history.append({"role": "user", "content": query})   # ① 追加 user 消息
        agent_loop(history)                                  # ② 核心循环

        # ③ 打印最终回答:history[-1] 必然是最后的 assistant 消息
        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)
        print()
