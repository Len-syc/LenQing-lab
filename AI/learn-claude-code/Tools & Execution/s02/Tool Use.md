`Tool dispatch map`
- Add a Tool, Add Just One Line
- The loop stays stable while capabilities register into a dispatch table.
---
this is s01
### 只有 bash 一个工具

s01 的 Agent 只有一个 bash 工具。读文件要 `cat`，写文件要 `echo "..." > file.py`，改文件要 `sed`。

模型想的是"读这个文件"，却要拼出 `cat path/to/file`。多了一层翻译，浪费 token，还容易拼错。
![](image/Pasted%20image%2020261018135405.png)


---

### s02

![](image/Pasted%20image%2020261018134954.png)
this lesson is easy.we just need understand this map
and
this is the dispatch map
![](image/Pasted%20image%2020261018135059.png)

what new than s01?
![](image/Pasted%20image%2020261018135156.png)



给 Agent 加一个工具只需要做两件事：

1. **定义工具**：在 `TOOLS` 数组里加一条描述
2. **注册处理函数**：在 `TOOL_HANDLERS` 字典里加一个映射







---

## 从 1 个工具到 5 个工具

s01 只有一个 bash：

```python
TOOLS = [{"name": "bash", ...}]

def run_bash(command): ...
```

s02 加到 5 个，每个工具都是独立定义：

```python
TOOLS = [
    {"name": "bash",       "description": "Run a shell command.", ...},
    {"name": "read_file",  "description": "Read file contents.",  ...},
    {"name": "write_file", "description": "Write content to file.", ...},
    {"name": "edit_file",  "description": "Replace text in file once.", ...},
    {"name": "glob",       "description": "Find files by pattern.", ...},
]
```

每个工具有自己的实现函数：

```python
def run_read(path, limit=None):
    lines = safe_path(path).read_text(encoding="utf-8").splitlines()
    if limit:
        lines = lines[:limit]
    return "\n".join(lines)

def run_write(path, content):
    safe_path(path).write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"

def run_edit(path, old_text, new_text):
    text = safe_path(path).read_text(encoding="utf-8")
    if old_text not in text:
        return "Error: text not found"
    safe_path(path).write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Edited {path}"

def run_glob(pattern):
    import glob as g
    matches = sorted(set(g.glob(
        pattern, root_dir=WORKDIR, recursive=True)))
    shown = matches[:200]
    if len(matches) > 200:
        shown.append("... (more matches omitted; narrow the pattern)")
    return "\n".join(shown)
```

---

## 工具分发

```python
TOOL_HANDLERS = {
    "bash":       run_bash,
    "read_file":  run_read,
    "write_file": run_write,
    "edit_file":  run_edit,
    "glob":       run_glob,
}

# 循环里只改了一行——从硬编码 run_bash 变成查表：
for block in tool_calls:
    handler = TOOL_HANDLERS[block.name]    # 查表
    output = handler(**block.input)         # 调用
    results.append(...)
```



## 速查

| 概念            | 一句话                           |
| ------------- | ----------------------------- |
| TOOL_HANDLERS | 工具名 → 处理函数的字典。加工具 = 加一行映射     |
| 工具定义          | 告诉模型"我能做什么"的 JSON schema      |
| 多工具调用         | 模型可一次返回多个 tool_use，并按原始顺序逐个执行 |


---

## 相对 s01 的变更

| 组件   | 之前 (s01)                        | 之后 (s02)                     |
| ---- | ------------------------------- | ---------------------------- |
| 工具数量 | 1 (bash)                        | 5 (+read, write, edit, glob) |
| 工具执行 | 硬编码 `run_bash()`                | TOOL_HANDLERS 查表分发           |
| 路径安全 | 无                               | safe_path 校验（仅 file tools）   |
| 循环   | `while True` + `tool_use` block | 与 s01 完全一致                   |










## 总结
简单来说，就只多了这些代码
![](image/Pasted%20image%2020261018220849.png)
``` py
# -- New in s02: tool definitions (one tool in s01, five in s02) --

  

TOOLS = [

    {"name": "bash", "description": "Run a shell command.",

     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},

    {"name": "read_file", "description": "Read file contents.",

     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},

    {"name": "write_file", "description": "Write content to a file.",

     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},

    {"name": "edit_file", "description": "Replace exact text in a file once.",

     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},

    {"name": "glob", "description": "Find files matching a glob pattern; ** matches recursively.",

     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},

]

  

# -- New in s02: dispatch map (replaces s01's hard-coded run_bash call) --

  

TOOL_HANDLERS = {

    "bash": run_bash, "read_file": run_read, "write_file": run_write,

    "edit_file": run_edit, "glob": run_glob,

}
```


