`Lifecycle hooks`
- Cross-cutting behavior belongs around the loop, not tangled inside it.
- “Hang on the Loop, Don't Write into It”----Hooks inject extension logic before and after tool execution.
## Problem
The s03 Agent has permission checks. But every new check, "log every bash call", "auto git add after writes", requires modifying the `agent_loop` function.

The loop quickly becomes this:

```python
def agent_loop(messages):
    while True:
        # ... LLM call ...
        for block in response.content:
            if block.type != "tool_use":
                continue
            log_to_file(block)          # added a line
            check_permission(block)     # added a line
            notify_slack(block)         # added another line
            output = execute(block)
            auto_git_add(block)         # yet another line
            # ... the loop is unrecognizable
```

What you want to extend is the Agent's behavior, but what you're modifying is the loop itself. The loop should be a stable core; extensions should hang on the outside.
and the hook likes the decorator in python

---


## The Solution

![](image/Pasted%20image%2020261020211153.png)s03 的循环和权限逻辑完全保留。唯一的变动是把 `check_permission()` 从循环体内移到了 hook 上，循环不再直接调用任何检查函数，改为 `trigger_hooks("PreToolUse", block)`，由注册表决定跑什么。
这里也体现出了一个思维，那就是,Minimal agent loop

---

Hook一共包含了四个事件
![](image/Pasted%20image%2020261020211957.png)
由此可见，agent loop就只需要做最简单的循环的就可以了，我们只需把想做的东西放在hook，避免再次去修改核心函数
如需扩展，通过 `register_hook()` 添加，循环只调用 `trigger_hooks()`

---
## Execution Flow

![](image/Pasted%20image%2020261020220025.png)

---
## How It Works
**Hook registry**: a dict mapping event names to callback lists.

```python
HOOKS = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
}

def register_hook(event: str, callback):
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:   # return value ≠ None → hook says "stop"
            return result
    return None
```

`PreToolUse` 返回非 `None` 时，本次工具执行被阻止；`Stop` 返回非 `None` 时，循环继续。`UserPromptSubmit` 和 `PostToolUse` 的返回值不参与控制流。后两者相当于执行层吧

---

**UserPromptSubmit** 在用户输入提交后、进入 LLM 前触发。以下 hook 记录当前工作目录：

```python
def context_inject_hook(query: str) -> str | None:
    """Inject current working directory info into every prompt."""
    print(f"\033[90m[HOOK] UserPromptSubmit: working in {WORKDIR}\033[0m")
    return None   # return None = no modification, let prompt through

register_hook("UserPromptSubmit", context_inject_hook)
```
这个理解简单，用来记录user的message
在主循环中，用户输入后立即触发：
```python
query = input("s04 >> ")
trigger_hooks("UserPromptSubmit", query)   # ← 进入 LLM 之前
history.append({"role": "user", "content": query})
agent_loop(history)
```


---
**PreToolUse / PostToolUse**，工具执行前后的 hook。s03 的权限检查逻辑现在包装成 PreToolUse hook，再加一个日志 hook 和一个大输出提醒：

```python
# PreToolUse: 权限检查（s03 的逻辑，从循环移到 hook）
def permission_hook(block):
    if block.name == "bash":
        for pattern in DENY_LIST:
            if pattern in block.input.get("command", ""):
                return "Permission denied by deny list"
    if block.name in ("read_file", "write_file", "edit_file"):
        path = block.input.get("path", "")
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            choice = input("   Allow? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "Permission denied by user"
    return None

# PreToolUse: 日志
def log_hook(block):
    print(f"[HOOK] {block.name}(...)")

# PostToolUse: 大文件提醒
def large_output_hook(block, output):
    if len(str(output)) > 100000:
        print(f"[HOOK] ⚠ Large output from {block.name}")

register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
```

---

**Stop** 在循环即将退出时触发。以下 hook 打印收尾统计：

```python
def summary_hook(messages: list) -> str | None:
    """Print a summary when the loop is about to stop."""
    tool_count = sum(1 for m in messages
                     for b in (m.get("content") if isinstance(m.get("content"), list) else [])
                     if isinstance(b, dict) and b.get("type") == "tool_result")
    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None   # return None = allow stop, return string = force continuation

register_hook("Stop", summary_hook)
```
统计本次调用了几轮工具

---
在 agent_loop 中，退出前触发：
先看看stop注册的函数是什么
`register_hook("Stop", summary_hook)`，是summary_hook
- **summary_hook 只做一件事：数整个会话一共执行了多少次工具调用** ，- 它数的是 `tool_result`，不是 `tool_use`（效果等价，但代码里写的是前者）
- 它**不判断、也不输出任何 text 消息**。无论有没有工具调用，它都只打印这一行灰色的统计，然后返回 `None`。
``` py

```
```python
tool_calls = [
    block for block in response.content if block.type == "tool_use"
]
if not tool_calls:
    force = trigger_hooks("Stop", messages)   # ← 退出之前
    if force:
        # hook returned a message → inject it and continue
        messages.append({"role": "user", "content": force})
        continue
    return
```

---

**循环里只改了一处**：s03 直接调用 `check_permission(block)`，s04 改为 `trigger_hooks("PreToolUse", block)`：

```python
for block in tool_calls:
    # s03: if not check_permission(block): ...
    # s04: hook 替代硬编码
    blocked = trigger_hooks("PreToolUse", block)
    if blocked:
        results.append({"type": "tool_result", "tool_use_id": block.id,
                        "content": str(blocked)})
        continue

    handler = TOOL_HANDLERS.get(block.name)
    output = handler(**block.input) if handler else f"Unknown: {block.name}"

    trigger_hooks("PostToolUse", block, output)

    results.append({"type": "tool_result", "tool_use_id": block.id,
                    "content": output})
```

四个 hook 覆盖了 agent cycle 的关键节点：输入→执行前→执行后→退出。循环只负责调用 trigger_hooks()，具体逻辑全在 hook 回调里。

---

## 相对 s03 的变更

| 组件      | 之前 (s03)                   | 之后 (s04)                                                                        |
| ------- | -------------------------- | ------------------------------------------------------------------------------- |
| 扩展方式    | check_permission() 硬编码在循环里 | HOOKS 注册表 + trigger_hooks()                                                     |
| 新函数     | —                          | register_hook, trigger_hooks                                                    |
| hook 回调 | —                          | context_inject_hook, permission_hook, log_hook, large_output_hook, summary_hook |
| 循环      | 直接调用 check_permission()    | 调用 trigger_hooks("PreToolUse", ...)                                             |
| 退出控制    | 无                          | trigger_hooks("Stop", ...) 可阻止退出                                                |
| 输入拦截    | 无                          | trigger_hooks("UserPromptSubmit", ...) 可注入上下文                                   |

---

## log
```txt
s04 >> Create a file called test.txt
[HOOK] UserPromptSubmit: working in D:\WorkSpace\AI\AI Project\learn-claude-code\s04_hooks
[HOOK] write_file(['', 'D:\\WorkSpace\\AI\\AI Project\\learn-claude-code\\s04_)
[HOOK] Stop: session used 1 tool calls
已创建文件 `test.txt`（空文件），位于 `D:\WorkSpace\AI\AI Project\learn-claude-code\s04_hooks\` 目录下。

需要往里面写入一些内容吗？

s04 >> Delete all temporary files in /tmp
[HOOK] UserPromptSubmit: working in D:\WorkSpace\AI\AI Project\learn-claude-code\s04_hooks
[HOOK] bash(['if exist C:\\tmp (dir C:\\tmp) else (echo "C:\\tmp does no)
[HOOK] bash(['dir "%TEMP%" | findstr /C:"个文件" /C:"File(s)" /C:"目录" /C:"D)
[HOOK] bash(['dir "%TEMP%"'])

[permission] Potentially destructive command
   Tool: bash({'command': 'del /q "%TEMP%\\*.tmp" 2>nul & dir "%TEMP%\\*.tmp" /b 2>nul & echo ---DONE---'})
   Allow? [y/N] n
[HOOK] Stop: session used 5 tool calls
删除操作被拒绝了，我没有执行任何删除。

仅供参考，当前临时目录 `C:\Users\Lenqin\AppData\Local\Temp` 中有 36 个 `.tmp` 文件（约 23 MB）。如果你改变主意，可以告诉我：

1. **删除全部 `.tmp` 文件** —— 执行刚才被拒绝的命令
2. **只删除特定文件** —— 比如指定文件名
3. **保持现状** —— 不做任何操作

需要怎么处理？

s04 >>
```

---


## Common mistakes
![](image/Pasted%20image%2020261020221508.png)
-  UserPromptSubmit有个作用，那就是context injection，但目前的代码里是只有打印给用户看，没有上下文注入这个功能，但是是有的，比如：自动附带的目录、git 状态、日期等信息都是通过这个实现，用来补充模型不知道的环境信息。如果后续加入git状态等等的话，也就要把这些消息和user的消息拼在一起然后一起发给llm。
	但又引发了一个问题，注入的消息重复，有2种solution，1.只注入第一次，并放入CLAUDE.md，动态信息放 system 里，每次请求现算。这些先不管


---


## Design Decisions
### Hook 包裹循环，而不是改写循环
UserPromptSubmit、PreToolUse、PostToolUse、Stop 等 hook 挂在生命周期节点上，模型-工具-结果循环本身保持不变。
### PreToolUse 是策略边界
PreToolUse 在模型选择工具之后、handler 执行之前运行。这是权限、日志和安全策略最自然的插入点。
### PostToolUse 让结果可观察
PostToolUse 可以检查输出大小、记录 trace 或转换元数据，而不需要修改每个工具 handler。



---
end.