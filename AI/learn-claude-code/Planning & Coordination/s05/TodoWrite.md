`An Agent Without a Plan Drifts Off Course`
- Explicit plans keep long-running work visible and correctable.

![[Pasted image 20261021174942.png]]
---

## 问题

给 Agent 一个复杂任务："把所有 Python 文件改成 snake_case 命名，然后跑测试，修好失败。"

Agent 开始干活，改了 3 个文件，跑了个测试，发现 2 个失败，开始修。修着修着，它忘了最初是"改成 snake_case"，测试失败把注意力全吸走了。

对话越长越严重：工具结果不断填满上下文，系统提示的影响力被稀释。一个 10 步重构，做完 1-3 步就开始即兴发挥，因为 4-10 步已经被挤出注意力了。



## 解决方案

![[Pasted image 20261021165823.png]]

S05 保留 S04 的工具分发、权限检查和 Hooks
再加入 `todo_write` 与 reminder 计数器。
`todo_write` 只更新计划状态，实际工作仍由原有工具完成。

新工具仍通过 `TOOL_HANDLERS[block.name]` 分发：相当于在tool那注册了`todo_write`

**代码层面**：连续三个工具调用轮次没有使用 `todo_write` 时，Harness 会把 reminder 追加到第三轮的工具结果中。



## How It Works
**TodoManager** 持有内存中的任务列表，负责校验更新，并把渲染结果返回给模型。`run_todo_write` 同时把这份状态打印到终端：

```python
class TodoManager:
    def __init__(self):
        self.items = []

    def update(self, todos: list | str) -> str:
        # Parse and validate before replacing the current list.
        validated = []
        ...
        self.items = validated
        return self.render()

    def render(self) -> str:
        # [ ] pending, [>] in progress, [x] completed
        ...


TODO = TodoManager()

def run_todo_write(todos: list | str) -> str:
    output = TODO.update(todos)
    print(output)
    return output
```
一次更新最多包含 20 项；每项都必须有非空的 `content`；同一时间只能有一个 `in_progress`。字符串输入可以是 JSON，也可以是 Python 列表表示，解析过程不使用 `eval`。

---

工具定义和其他 5 个工具一起加入 dispatch map：

```python
TOOLS = [
    {"name": "bash",       ...},
    {"name": "read_file",  ...},
    {"name": "write_file", ...},
    {"name": "edit_file",  ...},
    {"name": "glob",       ...},
    # s05: 新增一条
    {"name": "todo_write", "description": "Create and manage a task list ...",
     "input_schema": {
         "type": "object",
         "properties": {
             "todos": {
                 "type": "array",
                 "items": {
                     "type": "object",
                     "properties": {
                         "content": {"type": "string"},
                         "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                     },
                 },
             },
         },
     },
    },
]

TOOL_HANDLERS["todo_write"] = run_todo_write
```


---

**Reminder**：连续三个工具调用轮次没有使用 `todo_write` 时，reminder 会追加到第三轮的结果中，随后计数器清零：

```python
rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
if rounds_since_todo >= 3:
    results.append({
        "type": "text",
        "text": "<reminder>Update your todos.</reminder>",
    })
    rounds_since_todo = 0
```

---
Agent 收到任务后的典型流程：先调 `todo_write` 列出所有步骤（全 `pending`）→ 做一个步骤，改成 `in_progress` → 做完改成 `completed` → 看下一个 `pending` → 继续。


---

## Code
### class TodoManager
tool中的todo_write通过schema 教模型该怎么填，这是软约束
而TodoManager是代码层面的约束，它是硬约束，它负责：清洗入参、执行 schema 表达不了的业务规则（最多一条 in_progress）、整体替换状态，最后渲染成清单回喂给模型。
```py
if in_progress_count > 1:
    raise ValueError("Only one todo can be in_progress at a time")
```
同一时刻只允许一条任务“进行中”,从代码层面来逼模型一次只专注做一件事。

---
## 相对 s04 的变更

| 组件        | 之前 (s04)                          | 之后 (s05)                                  |
| --------- | --------------------------------- | ----------------------------------------- |
| 工具数量      | 5 (bash, read, write, edit, glob) | 6 (+todo_write)                           |
| 规划能力      | 无                                 | 带状态的 TODO 列表 + reminder                   |
| SYSTEM 提示 | 通用提示                              | 加入 "先计划再执行" 引导                            |
| 循环        | 工具分发与 Hooks                       | 保留分发路径，加入 rounds_since_todo 和 reminder 注入 |
![[Pasted image 20261021175330.png]]


## 设计决策

**TodoWrite 是工具，不是隐藏规划器**
规划通过和 bash、read_file 相同的工具分发路径进入系统。这样计划状态可见，模型也能决定何时更新。

**轻量提醒防止计划漂移**
多个回合没有更新 todo 后，运行时会注入提醒。它只提醒模型，不接管计划。

**当前 Todo 保持会话内状态**
TodoWrite 面向当前会话的工作计划，不是持久项目管理。后面的任务系统负责持久工作。