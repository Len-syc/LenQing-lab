`Permission gate`
- Check Permissions Before Execution
- Dangerous actions need a harness decision point before the shell runs.

---
`Beginner rule: the model proposes tools; the runtime routes each request to allow, ask, o[^1]r deny before execution.`

**Three Requests, Three Routes**
Permission is a router: safe calls run, risky calls ask, forbidden calls stop.
![](image/Pasted%20image%2020261018203135.png)
---
## Execution Flow
![](image/Pasted%20image%2020261018200836.png)


---
## **3个Gate**
- Gate 1: hard deny ---直接deny
- Gate 2: allow rule/risk rule
	- Gate 3: user approval

现在走一遍流程，一个Tool Request会走3个gate,当时Gate 1: hard deny的时候，deny，gate2的时候，如果是 allow rule--> allow,如果是 risk rule--> ask user
	![](image/Pasted%20image%2020261018203252.png)
### Gate 1: hard deny
forbidden root delete
![](image/Pasted%20image%2020261018202707.png)


### Gate 2: risk rule/allow rule
allow rule：此时它match到了Gate2,然后又是allow rule 随后被allow，这一步是自动，不需要ask user
![](image/Pasted%20image%2020261018202345.png)



---


risk rule：此时它match到了Gate2,然后又是risk rule (可能local destructive command)，所以 ask user(Deleting files needs an explicit approval ticket.)
	![](image/Pasted%20image%2020261018202521.png)
	![](image/Pasted%20image%2020261018202624.png)






---








## Code
![](image/Pasted%20image%2020261018220913.png)
### Part Code
#### gate 1：一张硬拒绝表，先查，命中就返回阻止信息。这张表使用简单字符串匹配来说明权限闸门的位置，不能视为完整的安全边界。

```python
DENY_LIST = [
    "rm -rf /", "sudo", "shutdown", "reboot",
    "mkfs", "dd if=", "> /dev/sda",
]

def check_deny_list(command: str) -> str | None:
    for pattern in DENY_LIST:
        if pattern in command:
            return f"Blocked: '{pattern}' is on the deny list"
    return None
```

#### gate 2负责规则匹配，用来描述"什么时候需要问用户"。每条规则指定工具和检查条件。

```python
import re

DESTRUCTIVE_COMMAND_WORD = re.compile(
    r"(?i)(?:^|[;&|()\n])\s*(?:rm|del)(?=\s|$|[;&|()])"
)

def contains_destructive_command(command: str) -> bool:
    return bool(DESTRUCTIVE_COMMAND_WORD.search(command))

PERMISSION_RULES = [
    {
        "tools": ["read_file", "write_file", "edit_file"],
        "check": lambda args: not (WORKDIR / args.get("path", "")).resolve().is_relative_to(WORKDIR),
        "message": "Access outside workspace",
    },
    {
        "tools": ["bash"],
        "check": lambda args: contains_destructive_command(args.get("command", "")) or any(
            kw in args.get("command", "") for kw in ["rm ", "> /etc/", "chmod 777"]
        ),
        "message": "Potentially destructive command",
    },
]

def check_rules(tool_name: str, args: dict) -> str | None:
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return None
```

#### gate 3：规则命中后，暂停等用户输入。

```python
def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n⚠  {reason}")
    print(f"   Tool: {tool_name}({args})")
    choice = input("   Allow? [y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"
```

**三道闸门串在一起**，插在工具执行之前：

```python
def check_permission(block) -> bool:
    # 闸门 1: 硬拒绝
    if block.name == "bash":
        reason = check_deny_list(block.input.get("command", ""))
        if reason:
            print(f"\n⛔ {reason}")
            return False

    # 闸门 2 + 3: 规则匹配 → 用户审批
    reason = check_rules(block.name, block.input)
    if reason:
        decision = ask_user(block.name, block.input, reason)
        if decision == "deny":
            return False

    return True

# 在 agent_loop 中——s02 的循环只加了一行：
for block in tool_calls:
    if not check_permission(block):           # ← 新增
        results.append({... "content": "Permission denied."})
        continue
    output = TOOL_HANDLERS[block.name](**block.input)  # s02 原有
    results.append(...)
```





---


## Design Decisions
**三道门让策略可解释**
	硬拒绝、规则匹配、用户确认是分开的关卡。这样能看清命令是绝对禁止、有风险，还是只是在等确认
**被拦截的调用也要留下循环状态**
	被拦截的工具调用仍然要让循环状态保持一致。用户和模型都需要知道为什么没有执行，才能决定下一步。