`Minimal model/tool loop`
- One Loop Is All You Need
- The smallest useful agent is a loop that calls the model, runs tools, and feeds results back.
# Agent_loop
![[Pasted image 20261014232327.png]]
![[Pasted image 20261015123941.png]]

---
## step1
message[] accumulated message list
``` py
messages = [{"role": "user", "content": query}]
```
## step2
Send the messages and tool definitions to the LLM.
the step1 only include the user’s message
``` py
response = client.messages.create(
    model=MODEL, system=SYSTEM, messages=messages,
    tools=TOOLS, max_tokens=8000,
)
```
the system is system prompt and remember that the message only include the user and assistant message also tools result

## step3
step3 responsible for parsing the message and get what tools will be executed
The execution of the tool happens in step4
``` py
messages.append({"role": "assistant", "content": response.content})
tool_calls = [
    block for block in response.content if block.type == "tool_use"
]
if not tool_calls:
    return
```
see this code we receive the message from llm and parsing the message,if there is `tool_calls` in the `response.content` the code(harness) will execution it(tools) in step4
Only concrete `tool_use` blocks enter the execution stage, so the loop never appends an empty tool-result message.

## step4
Execute the tool the model requested and collect the results.
``` py
results = []
for block in tool_calls:
    output = run_bash(block.input["command"])
    results.append({
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": output,
    })
```

## Step 5
Append the tool results as a new message and go back to Step 2.
``` py
messages.append({"role": "user", "content": results})
```

## Assembled into a complete function:

``` py
def agent_loop(messages):
    while True:
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )//step2
        messages.append({"role": "assistant", "content": response.content})
        tool_calls = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_calls:
            return
		//step3
        results = []
        for block in tool_calls:
            output = run_bash(block.input["command"])
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })
        //step4
        messages.append({"role": "user", "content": results})
        //step5
```
 It's not intelligence itself, but the smallest runtime framework that lets the model keep acting. The model decides (whether to call a tool, which one), the harness executes (calls the tool and appends the result as a new message). The next 16 chapters all add mechanisms on top of this loop. The loop itself never changes.





---

## code
``` py
        try:

            # \001/\002 tell Readline the ANSI escapes have zero display width.

            query = input("\001\033[36m\002s01 >> \001\033[0m\002")

        except (EOFError, KeyboardInterrupt):

            break

        if query.strip().lower() in ("q", "exit", ""):

            break

        history.append({"role": "user", "content": query})
```
这一段负责的是用户的input
之后就把`agent_loop(history)`message[] 放进去

![[Pasted image 20261015211706.png]]


之后就是这一段，在想看懂这一段之前，要先了解a/的api格式。
	它的message[]长这样：{"role": "user" 或 "assistant", "content": ???}
		其中**`content` 有两种形态**——纯字符串，或者“内容块(block)列表":
**!!!!**记住，用户输入的消息始终是content: "你好"  这种形式的

``` text
content: "你好"                        ← 字符串形态(简单消息)
content: [ 块1, 块2, ... ]             ← 列表形态(涉及工具时必须用这个)
```

然后块呢又分几种类型
| 块类型 | 出现在 | 长什么样 |
| :--- | :--- | :--- |
| `text` | assistant | 模型说的自然语言 |
| `tool_use` | assistant | 模型想调工具:"帮我执行 ls" |
| `tool_result` | user | 工具执行结果回喂给模型 |
``` text
history = [

  ① {"role": "user",
     "content": "这个目录有什么文件?"},                  ← 你输入的,字符串形态

  ② {"role": "assistant",
     "content": [ TextBlock(type="text", text="我来看一下"),
                  ToolUseBlock(type="tool_use", id="toolu_01",
                               name="bash",
                               input={"command": "ls"}) ]},   ← 模型边说边调工具

  ③ {"role": "user",
     "content": [ {"type": "tool_result", "tool_use_id": "toolu_01",
                   "content": "code.py\nREADME.md"} ]},       ← 工具结果,必须放 user 里

  ④ {"role": "assistant",
     "content": [ TextBlock(type="text",
                  text="目录下有 code.py 和 README.md 两个文件。")]},  ← 最终回答,没有 tool_use
]
```
tools的result是属于user的
`response_content = history[-1]["content"]`这个是负责提取出这个块的最后一个，也就是④，这属于assistant的最终回答
`if isinstance(response_content, list):`
是为了防止content是string而不是list,之后的代码就是遍历，然后把string打印出来
``` py
for block in response_content:
    if getattr(block, "type", None) == "text":
        print(block.text)
```
这种就是正常的情况，harness拿到了list[-1]。而这时候的content是属于block，block中的text类型，这段就负责把text提取出来。

---
完整流程：

![[Pasted image 20261015223415.png]]



---



！！ 顺带一提
a/的api格式中，content只包含user和assistant,那system prompt呢？
	答案是：它们是并联关系
``` py
while True:
    response = client.messages.create(
        model=MODEL,
        system=SYSTEM,      # ← 注意:循环里的每一次调用都带着它
        messages=messages,  # ← 这个才是在不断增长的对话历史
        tools=TOOLS, max_tokens=8000,
    )
```
``` text
┌─ 模型实际看到的输入 ──────────────────────────┐
│ [system] You are a coding agent at D:\...    │ ← 来自 system 参数
│ [tools]  bash: Run a shell command...        │ ← 来自 tools 参数
│ [user]   这个目录有什么文件?                    │ ┐
│ [assistant] (我想执行 ls) tool_use             │ │ 来自 messages 数组,
│ [user]   tool_result: code.py README.md      │ │ 按顺序拼在后面
└──────────────────────────────────────────────┘
```
但openai的api格式中,content有user/assistant/system
a/的优点，
1. **语义干净**：system 是“设定”，不是“对话的一部分”。它不占轮次，永远不会出现“模型回复了系统提示”这种怪事；
2. **校验简单**：messages 数组只需遵守“user/assistant 严格交替”这一条规则，不会因为插了一条 system 消息把交替关系搞乱；
3. **便于缓存**：system 和 tools 通常固定不变，messages 不断增长。分开放，配合 prompt caching 可以只缓存不变的前缀，省钱省时间。


## Design Decisions
### Recursive Process Spawning as Subagent Mechanism
子代理很好理解，你可以把它当做一个tools
``` text
你输入: "调研一下这个仓库的目录结构并总结"
│
▼
┌─ 父 Agent 进程 (python v0.py) ─────────────────┐
│ history = [你的问题, 助手回复, 工具结果, ...]      │
│ LLM 思考: "细节调查太占上下文,派个下属去干"        │
│ 输出 tool_use: bash 执行                         │
│   python v0.py "列出所有顶层目录并说明用途"        │
│                                                 │
│   run_bash() 调 subprocess.run()                │ 可以看到，这里本质就是调用tools.
│   ──── 操作系统创建了一个全新的进程 ────           │
│   ▼                                             │
│ ┌─ 子 Agent 进程 (python v0.py "子任务") ─┐      │
│ │ 从 main 开始执行,history = [],一片空白    │      │
│ │ 第一条消息 = 命令行参数里的子任务          │      │
│ │ system prompt 是代码里写死的那份          │      │
│ │ 自己跑自己的循环:                         │      │
│ │   LLM → ls → LLM → cat → LLM → ...      │      │
│ │   (可能 20 轮,产生 20 条中间结果)          │      │
│ │ 模型不再调工具 → 打印最终总结到 stdout     │      │
│ │ 进程退出 ✝                               │      │
│ └─────────────────────────────────────────┘      │
│                                                 │
│ subprocess.run() 的返回值 = 子进程的 stdout      │
│ 这段总结文本作为普通 tool_result 喂回父 LLM       │
│ 父 LLM 看着总结,继续干活                          │
└─────────────────────────────────────────────────┘ 最后只返回result.
```

为什么要这么做？——“隔离”的价值
	假设父 Agent 自己去调研目录结构，会产生 20 多轮工具调用、几万字中间输出，全部塞进主对话的上下文，很快就把窗口撑爆。
	派给子 Agent 后：那 20 轮肮脏细节全部发生在子进程自己的上下文里，**父对话里只多了一条工具结果——最终那 10 行总结**。这就是 "naturally isolates concerns"(天然的关注点隔离)。
- 可以看到 v0直接 `python v0.py "子任务"`,纯进程派生。最简单，但没法控制子 Agent——它有和父 Agent 一样的全部工具，返回的只有 stdout 文本。
- **框架级 Task 工具**(v3 的方案，也是 Claude Code 真实的做法)：把“启动子代理”做成一个正式的工具，这样可以精细控制——**限制子 Agent 能用哪些工具**(比如不许它再派生子 Agent,防止无限递归)、**返回结构化结果**、加轮数上限、挂 hooks 等。

！Task 工具的本质不是魔法，而是“
再跑一遍 agent loop”——进程派生就是最原始的实现。







### No Planning Framework -- The Model Decides
这个更简单，传统做法是写一个规划器，任务队列，状态器。但有个问题，这种是代码写死的，属于是pipe.
正如序章说的，harness不是pipe.
所以才有了这个v2
``` text
模型调 todo_write 工具
        │
        ▼
框架的 TodoManager 存下清单 ──────────────┐
        │                                │
        │ 注入模型上下文(随工具结果/提醒)    │ 渲染成 UI 面板
        ▼                                ▼
   模型每轮重新"读到"清单              人看着面板
   → 对齐计划,决定下一步
   → 做完更新状态
```
ai拥有自主权，决策权，harness只负责给它环境
简单来说就是：![[Pasted image 20261016215638.png]]






### Why Bash Alone Is Enough

**bash 是万能工具，加别的工具不增加能力，只增加混乱。**

- **能力上**：读文件(`cat`)、写文件(`echo >`)、跑任意程序、管理文件系统，bash 全都能干。所以 `read_file` 这类专用工具只是 bash 能力的**子集**，加了也不会解锁新功能；
- **代价上**：每加一个工具，模型就多一份 schema 要学、多一次“选哪个”的判断，代码也多一份要维护。加工具 = 加出错面；
- **结论**：最小可用 Agent = **一个循环 + 一个 shell**。"LLM + shell”本身就已经是通用 Agent 了；
- **为什么不一开始就堆满工具**(ALTERNATIVES):那样会掩盖这个核心洞察，而且从最小版开始，后面每个版本“加了什么、为什么加”一目了然。
**先用最少的工具证明能力，再谈其他。**
---

## 完整流程
![[Pasted image 20261015191859.png]]![[Pasted image 20261015191912.png]]![[Pasted image 20261015191927.png]]
![[Pasted image 20261016215003.png]]


### 数据流程：
1. system、tools 每次调用都传，但**永不进 history**;
2. API 无状态，**记忆 = 客户端维护的 history**;
3. 每轮循环**两次追加**：先 assistant 回复，再 tool_result(role：user)；
4. tool_use 和 tool_result **分为两条消息**，靠 `tool_use_id`来标识 
	1. - `tool_use` 块上的字段叫 **`id`**(编号的“原件”，API 每次调用现生成的)；
	2. - `tool_result` 块上的字段叫 **`tool_use_id`**(“复印件”，意思是我回答的是**哪个** tool_use)。
---

用户 "目录里有什么文件?"
   │
   ▼
┌─────────── 第 1 次调用 ───────────┐
│ 发: system + TOOLS + history(1条) │
│ 回: [text块, tool_use块(id=A)]     │
└──────────────┬────────────────────┘
   追加②assistant     追加③tool_result(tool_use_id=A, user外衣)
   执行 dir ──────────────► output 字符串
   ▼
┌─────────── 第 2 次调用 ───────────┐
│ 发: system + TOOLS + history(3条) │  ← system/tools 每次重传,API 无状态
│ 回: [text块]  stop_reason=end_turn │
└──────────────┬────────────────────┘
   追加④assistant → 无 tool_use → 停
   ▼
打印 history[-1] 里的 text 块


---

**init**
``` py
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))   # api_key 自动从 .env 读
MODEL  = "glm-5.3-flash"        # 来自 .env 的 MODEL_ID,决定"哪个大脑"

SYSTEM = "You are a coding agent. Use bash to solve tasks. Act, don't explain."

TOOLS = [
    {
        "name": "bash",                       # 模型引用工具时用的名字
        "description": "Run a shell command.",  # 给模型看的"说明书"
        "input_schema": {                     # 参数的 JSON 描述
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]           # 必填
        },
    }
]
```

**system 和 tools 不在 history 里**。它们是每次调用的独立参数，每次都要重新传，但永远不作为消息追加进对话。

---
code
``` py
query = "目录里有什么文件?"
history = []
history.append({"role": "user", "content": query})
```
user input
``` py
history = [
    {"role": "user", "content": "目录里有什么文件?"}     # 1 条
]
```


---
api request
``` py
response = client.messages.create(
    model="glm-5.3-flash",                    # ← 用哪个大脑
    system="You are a coding agent. Use bash...",  # ← 人设规则(独立参数!)
    messages=history,                         # ← 全部历史(此刻 1 条)
    tools=TOOLS,                              # ← 工具清单(独立参数!)
    max_tokens=8000,                          # ← 回复长度上限
)
```

---


API returns the full response
``` py
response = Message(
    id="msg_01XYZ",
    model="your-model-id",
    stop_reason="tool_use",        # ← API 侧的停止原因:想调工具
    content=[                      # ← response.content,块列表
        TextBlock(type='text', text='我来看看这个目录。'),
        ToolUseBlock(type='tool_use', id='toolu_01ABC', name='bash',
                     input={'command': 'dir'})
    ],
    usage=Usage(input_tokens=152, output_tokens=89),
)
```

---
append message
``` py
history.append({"role": "assistant", "content": response.content})   # 整串块原样
```

此时的history有：
``` py
history = [
    {"role": "user",      "content": "目录里有什么文件?"},
    {"role": "assistant", "content": [TextBlock('我来看看这个目录。'),
                                       ToolUseBlock(id='toolu_01ABC', ...)]}   # 2 条
]
```


---
Filter tool_use block

``` py
tool_calls = [b for b in response.content if b.type == "tool_use"]
# → [ToolUseBlock(id='toolu_01ABC', name='bash', input={'command': 'dir'})]
```
if tools_call not empty.continute the loop


---
Execute the tools and return the result

next

second append the message of tool_result --> role:user
``` py
history.append({
    "role": "user",
    "content": [{
        "type": "tool_result",
        "tool_use_id": "toolu_01ABC",    # ← 抄自第 2 步 ToolUseBlock.id
        "content": output                # ← 工具输出住进块的 content 字段
    }]
})
```

now there is the list of history
``` py
history = [
    ① {"role": "user",      "content": "目录里有什么文件?"},
    ② {"role": "assistant", "content": [text块, tool_use块(id=toolu_01ABC)]},
    ③ {"role": "user",      "content": [{type:'tool_result',
                                          tool_use_id:'toolu_01ABC',     # ← 认亲凭据
                                          content:" ...code.py README.md"}]}   # 3 条
]
```


---
the next api request

``` py
response = client.messages.create(
    model="your-model-id",
    system="You are a coding agent. Use bash...",   
    messages=history,                               # ^history内容如上
    tools=TOOLS,                                    
    max_tokens=8000,
)
```


---
api respond 
``` py
response = Message(
    id="msg_02DEF",
    stop_reason="end_turn",       
    content=[
        TextBlock(type='text', text='这个目录下有两个文件:code.py 和 README.md。')
    ],                             # ← 只有 text 块,没有 tool_use
)
```


---
next append first and check response.content
``` py
history.append({"role": "assistant", "content": response.content})   # 第 4 条
tool_calls = [b for b in response.content if b.type == "tool_use"]
# → []  空的 → return,循环结束
```

---
finnaly

print the assistant's message
``` py
for block in history[-1]["content"]:        # history[-1] = 第 4 条(必然是 assistant)
    if getattr(block, "type", None) == "text":
        print(block.text)                   # → "这个目录下有两个文件:..."
```


---


## Common mistakes
1. 调完 API 的第一件事：**把 `response.content` append到history**,然后才轮到“检查 tool_use”。**先收货入库，再验货。**
2. “agent_loop 退出时，`history[-1]` 必是 assistant 消息”
3. 用户的消息是{"content": "你好"}，模型返回的只能是block，然后追加tool_result的时候是以user的身份来的，但这时候也是block的形式，block里的text





























end.






