
	只要有一个任务需要被感知、推理和执行 -- agent 就需要一个 harness。


agent不是水管式的。


模型做决策。Harness 执行。模型做推理。Harness 提供上下文。模型是驾驶者。Harness 是载具。
```
Harness = Tools + Knowledge + Observation + Action Interfaces + Permissions
    Tools:          文件读写、Shell、网络、数据库、浏览器
    Knowledge:      产品文档、领域资料、API 规范、风格指南
    Observation:    git diff、错误日志、浏览器状态、传感器数据
    Action:         CLI 命令、API 调用、UI 交互
    Permissions:    沙箱隔离、审批流程、信任边界
```

```
编程 agent 的 harness 是它的 IDE、终端和文件系统。 农业 agent 的 harness 是传感器阵列、灌溉控制和气象数据。酒店 agent 的 harness 是预订系统、客户沟通渠道和设施管理 API。Agent -- 那个智能、那个决策者 -- 永远是模型。Harness 因领域而变。Agent 跨领域泛化。

这个仓库教你造载具。编程用的载具。但设计模式可以泛化到任何领域：庄园管理、农田运营、酒店运作、工厂制造、物流调度、医疗保健、教育培训、科学研究。只要有一个任务需要被感知、推理和执行 -- agent 就需要一个 harness。
```
	Harness（通用公式）
	= Tools + Knowledge + Observation + Action Interfaces + Permissions
	
	编程领域 Harness
	= 上面五类能力，主要通过：
	  IDE、终端、文件系统、Git、LSP、浏览器、沙箱、RAG…… 暴露给模型
	
	酒店领域 Harness
	= 同样五类能力，主要通过：
	  预订系统、客户沟通渠道、设施管理 API、PMS/CRM、支付、门锁/IoT、审批…… 暴露给模型
循环永远不变。工具在变。知识在变。权限在变。Agent = 模型(LLM) + 泛化的操作环境(Harness)。

```
设计：原子化、可组合、描述清晰。
```
	其实简单来说，要和积木一样，需要具备其，单一化，可组合化的思维方式，每一个需要明确的功能，·明确的界限，so u need a mind of moudel format.every function is a lonely moudel.


```
    策划知识。** 给 agent 领域专长。产品文档、架构决策记录、风格指南、合规要求。按需加载（s07），不要前置塞入。Agent 应该知道有什么可用，然后自己拉取所需。
```
	反例：System Prompt:
	  这是产品文档...
	  这是架构决策记录...
	  这是风格指南...
	  这是合规要求...
	  ...（共 50 万字）
	  “策划”（curated）意思是：**不是原始堆积，而是经过整理、分类、标注、可检索的知识。**
	  可用知识源：
	- product-docs: 产品功能、用户流程、错误码规范
	- adr: 架构决策记录，技术选型原因
	- style-guide: 代码风格、文案风格、命名规范
	- compliance: 隐私、安全、行业合规要求
	需要时用 search_docs 或 read_file 获取具体内容。
	
	Agent 看到这个目录，就知道：
	
	- 改文案 → 查 style-guide
	    
	- 改架构 → 查 adr
	    
	- 处理用户数据 → 查 compliance
	    
	- 改功能 → 查 product-docs


## THE AGENT PATTERN

```
                    THE AGENT PATTERN
                    =================

    User --> messages[] --> LLM --> response
                                      |
                              包含 tool_use block?
                           /                          \
                         yes                           no
                          |                             |
                    execute tools                    return text
                    append results
                    loop back -----------------> messages[]


    这是最小循环。每个 AI Agent 都需要这个循环。
    模型决定何时调用工具、何时停止。
    代码只是执行模型的要求。
    本仓库教你构建围绕这个循环的一切 --
    让 agent 在特定领域高效工作的 harness。
```


``` py
def agent_loop(messages):
    while True:
        response = client.messages.create(
            model=MODEL, system=SYSTEM,
            messages=messages, tools=TOOLS,
        )
        messages.append({"role": "assistant",
                         "content": response.content})

        tool_calls = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_calls:
            return

        results = []
        for block in tool_calls:
            output = TOOL_HANDLERS[block.name](**block.input)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })
        messages.append({"role": "user", "content": results})****
```
	
```text
	messages[] 
	   ↓
	发给 LLM
	   ↓
	得到 response
	   ↓
	把 response 追加到 messages
	   ↓
	response 里有 tool_use 吗？
	   ├─ 没有 → return，结束
	   └─ 有 → 执行工具，得到结果
	            ↓
	         把结果作为 user 消息追加到 messages
	            ↓
	         回到开头，再发给 LLM
```