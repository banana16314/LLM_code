# 自研 Ink 渲染引擎：在终端里跑一个 React

## 一句话理解

Claude Code 的终端界面不是简单地 `console.log` 输出文字。它背后是一个**完整的 UI 渲染引擎**——用 React 写组件，用 Yoga 做 Flexbox 布局，用双缓冲做差量更新，还支持滚动、焦点管理、鼠标点击和文本选择。这就是一个跑在终端里的"浏览器渲染引擎"。

> **比喻**：浏览器有 DOM → 布局 → 绘制 → 合成 这条渲染管线。Claude Code 在终端里重建了同样的管线：虚拟 DOM → Yoga 布局 → 屏幕缓冲区 → 差量输出到终端。

## 为什么不用现成的 Ink

[Ink](https://github.com/vadimdemedes/ink) 是 npm 上流行的终端 React 框架，但 Claude Code 选择了**完全自研**。主要原因：

| 需求 | Ink (npm) | 自研 Ink |
|------|-----------|----------|
| 全屏模式（Alt Screen） | 不支持 | 支持 |
| 鼠标点击/滚轮 | 不支持 | 支持 |
| 文本选择 + 搜索高亮 | 不支持 | 支持 |
| DECSTBM 硬件滚动 | 不支持 | 支持 |
| 性能级差量更新 | 基础 | Cell 级 diff + blit 优化 |
| 光标定位（IME 输入法） | 不支持 | 支持 |

## 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `ink.tsx` | 1722 | 主协调器：渲染循环、事件派发、选择/搜索 |
| `reconciler.ts` | 512 | React 接入层：虚拟 DOM 变更处理 |
| `log-update.ts` | 773 | 差量算法：生成终端补丁 |
| `screen.ts` | 1486 | 屏幕缓冲区：压缩 Cell 表示、池化 |
| `output.ts` | 797 | 渲染树 → 屏幕操作转换 |
| `render-node-to-output.ts` | 1462 | DOM 树遍历、裁剪、滚动处理 |
| `dom.ts` | 484 | 虚拟 DOM 节点管理 |
| `focus.ts` | 181 | 焦点系统 |

## 渲染管线：6 个阶段

```
React 组件树
    │
    ▼ 阶段 1: React 协调
┌────────────────────────┐
│   react-reconciler      │
│                         │
│ <Box flexDirection="row">│
│   <Text>Hello</Text>   │
│   <ScrollBox>...</>     │
│ </Box>                  │
│                         │
│  → 生成/更新虚拟 DOM     │
└──────────┬──────────────┘
           │
    ▼ 阶段 2: Yoga 布局
┌────────────────────────┐
│   calculateLayout()     │
│                         │
│  Flexbox 计算每个节点的  │
│  x, y, width, height    │
└──────────┬──────────────┘
           │
    ▼ 阶段 3: 渲染到缓冲区
┌────────────────────────┐
│ renderNodeToOutput()    │
│                         │
│  DFS 遍历 DOM 树        │
│  → 生成 Write/Blit/     │
│    Clear/Clip 操作      │
│  → 写入 Screen 缓冲区    │
└──────────┬──────────────┘
           │
    ▼ 阶段 4: 叠加层
┌────────────────────────┐
│  文本选择反色            │
│  搜索关键词高亮           │
└──────────┬──────────────┘
           │
    ▼ 阶段 5: 差量计算
┌────────────────────────┐
│ diffEach(prev, next)    │
│                         │
│  逐 Cell 对比            │
│  → 生成 Patch[] 补丁     │
└──────────┬──────────────┘
           │
    ▼ 阶段 6: 终端输出
┌────────────────────────┐
│  Patch → ANSI 转义序列   │
│  → 写入 stdout           │
└─────────────────────────┘
```

## 虚拟 DOM

### 节点类型

```typescript
// src/ink/dom.ts
type ElementNames =
  | 'ink-root'          // 根节点
  | 'ink-box'           // 容器（对应 <Box>）
  | 'ink-text'          // 文本（对应 <Text>）
  | 'ink-virtual-text'  // 嵌套文本（Text 内的 Text）
  | 'ink-link'          // 超链接（OSC 8）
  | 'ink-progress'      // 进度条
  | 'ink-raw-ansi'      // 预渲染的 ANSI 字符串
```

### 节点结构

```typescript
// src/ink/dom.ts
type DOMElement = {
  nodeName: ElementNames
  childNodes: DOMNode[]
  attributes: Record<string, DOMNodeAttribute>
  yogaNode?: LayoutNode        // Yoga 布局节点
  dirty: boolean                // 是否需要重新渲染

  // 滚动状态
  scrollTop?: number
  pendingScrollDelta?: number   // 待消耗的滚动距离
  scrollHeight?: number         // 内容总高度
  scrollViewportHeight?: number // 可视区高度

  // 焦点
  focusManager?: FocusManager

  // 事件处理器（存在这里避免每次 render 重新绑定）
  _eventHandlers?: Record<string, unknown>
}
```

### 脏标记传播

当一个节点发生变化时，脏标记会**向上传播到根节点**：

```typescript
// src/ink/dom.ts
function markDirty(node) {
  node.dirty = true
  if (node.parentNode) {
    markDirty(node.parentNode)  // 递归向上
  }
}
```

```
ink-root (dirty=true)  ← 传播到这里
  └── ink-box (dirty=true)  ← 传播到这里
        ├── ink-text (dirty=false)  // 没变，跳过
        └── ink-text (dirty=true)   // 内容变了
```

## 屏幕缓冲区：每个字符 8 字节

### Cell 压缩表示

普通实现每个 Cell 是一个对象（属性、样式、字符……），内存开销大。自研引擎把每个 Cell 压缩到**两个 Int32（8 字节）**：

```typescript
// src/ink/screen.ts
// 每个 Cell = 2 个 Int32

// 第 1 个 Int32: 字符 ID
word0 = charId  // 指向 CharPool 的索引

// 第 2 个 Int32: 打包的元数据
word1 = styleId << 17    // 高 15 位：样式 ID
      | hyperlinkId << 2 // 中间 15 位：超链接 ID
      | width             // 低 2 位：字符宽度

// 字符宽度
enum CellWidth {
  Narrow = 0      // 普通字符（1 列宽）
  Wide = 1        // CJK/emoji（2 列宽）
  SpacerTail = 2  // 宽字符的右半部分
  SpacerHead = 3  // 行末软换行的宽字符
}
```

> **设计思路**：用 `Int32Array` 而不是对象数组，有两大好处：
> 1. **内存**：对象每个至少 64 字节（V8 开销），Int32 只要 8 字节，省 8 倍
> 2. **比较**：diff 时比较两个 Int32 是一条 CPU 指令，比较对象要逐字段遍历

### 三大池化系统

字符、样式、超链接都通过**池化**去重：

```
┌──────────────────────────────────────────┐
│ CharPool                                  │
│                                           │
│ ID=0 → " " (空格)                         │
│ ID=1 → "H"                               │
│ ID=2 → "你" (2列宽)                       │
│ ID=3 → "🎉" (2列宽)                       │
│ ...                                       │
│                                           │
│ 同一个字符只存一份，Cell 中只存 ID          │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│ StylePool                                 │
│                                           │
│ ID=0 → ""（默认样式）                      │
│ ID=1 → "\x1b[1m"（加粗）                  │
│ ID=2 → "\x1b[31m"（红色）                 │
│ ...                                       │
│                                           │
│ 还缓存了样式转换字符串：                    │
│ (ID=0 → ID=2) → "\x1b[31m"               │
│ (ID=2 → ID=1) → "\x1b[0m\x1b[1m"         │
│ 热路径零分配                               │
└──────────────────────────────────────────┘
```

池会每 5 分钟重置一次，防止长时间运行导致无限增长。

### 屏幕操作

```typescript
// src/ink/screen.ts

// 整屏清除：用 BigInt64Array 一条指令清空
function resetScreen(screen) {
  screen.cells64.fill(0n)  // 每 8 字节一个 BigInt64，极快
}

// 区域复制：TypedArray.set() 一次性拷贝
function blitRegion(dst, src, rect) {
  for (let row = rect.top; row < rect.bottom; row++) {
    const srcSlice = src.cells.subarray(srcStart, srcEnd)
    dst.cells.set(srcSlice, dstStart)  // O(1) per row
  }
}
```

## 差量更新：只写变化的 Cell

每一帧渲染完成后，引擎会**逐 Cell 对比**前后两帧，只输出发生变化的部分：

```typescript
// src/ink/log-update.ts (lines 305-388)
function diffEach(prevScreen, nextScreen) {
  const patches = []

  for (let row = 0; row < height; row++) {
    for (let col = 0; col < width; col++) {
      const prevCell = prevScreen.cellAtIndex(i)
      const nextCell = nextScreen.cellAtIndex(i)

      // 两个 Int32 都相同 → 跳过（热路径，极快）
      if (prevCell.word0 === nextCell.word0
       && prevCell.word1 === nextCell.word1) continue

      // 跳过宽字符的占位 Cell（终端自动处理）
      if (nextCell.width === SpacerTail) continue

      // 生成补丁：移动光标 + 写入字符
      patches.push(
        { type: 'cursorTo', col },
        { type: 'styleStr', str: stylePool.transition(prevStyleId, nextStyleId) },
        { type: 'stdout', content: charPool.get(nextCell.charId) },
      )
    }
  }
  return patches
}
```

```
前一帧:                      当前帧:
┌──────────────────┐        ┌──────────────────┐
│ Hello World      │        │ Hello Claude     │  ← 只有这里变了
│ Status: running  │        │ Status: running  │  ← 完全相同，跳过
│ > _              │        │ > _              │  ← 完全相同，跳过
└──────────────────┘        └──────────────────┘

输出的终端指令：
  CSI 1;7H        (移动到第 1 行第 7 列)
  "Claude"        (只写变化的 6 个字符)
  CSI 1;13H       (移到 "World" 剩余位置)
  "     "         (清除多余字符)
```

## DECSTBM 硬件滚动优化

在全屏模式下，当 ScrollBox 滚动时，引擎不会重绘整个屏幕。而是利用终端的**滚动区域指令**（DECSTBM）让终端硬件完成滚动：

```
用户滚动 ↓ 3 行

传统方式（重绘全部）:              DECSTBM（硬件滚动）:
───────────────────              ───────────────────
发送 2000 个字符                  发送 ~50 个字符

CSI H                            CSI 3;20r    (设置滚动区域)
第1行的全部内容                    CSI 3S       (滚动 3 行)
第2行的全部内容                    CSI 18;1H    (移到新行)
第3行的全部内容                    新第18行的内容
...                              新第19行的内容
第20行的全部内容                   新第20行的内容
                                 CSI 1;999r   (重置滚动区域)
```

```typescript
// src/ink/log-update.ts (lines 165-185)
// 检测到 ScrollBox 的 scrollTop 变化时
if (altScreen && scrollDelta !== 0) {
  // 1. 在前一帧缓冲区上模拟滚动
  simulateScroll(prevScreen, scrollDelta)

  // 2. 生成 DECSTBM 指令
  patches.push({ type: 'stdout', content: `\x1b[${top};${bottom}r` })
  patches.push({ type: 'stdout', content: `\x1b[${delta}S` })

  // 3. diff 只需要找出滚动后"新露出"的行
  //    已经在屏幕上的内容不需要重传
}
```

## 脏区域追踪 + Blit 优化

不是每一帧都需要重新渲染整棵树。引擎使用**脏标记 + 区域复制**来跳过没变化的子树：

```
┌─────────────────────────────┐
│ ink-root                     │
│                              │
│ ┌──────────┐ ┌────────────┐ │
│ │ 侧边栏    │ │ 主内容区    │ │
│ │ (没变化)  │ │ (有变化)    │ │
│ │           │ │             │ │
│ │ blit 复制  │ │ 重新渲染    │ │
│ │ 前一帧的   │ │ 新内容      │ │
│ │ 对应区域   │ │             │ │
│ └──────────┘ └────────────┘ │
└─────────────────────────────┘
```

```typescript
// src/ink/render-node-to-output.ts
function renderNodeToOutput(node, prevScreen) {
  if (!node.dirty && canBlit) {
    // 这个子树没变化，直接从前一帧复制
    operations.push({
      type: 'blit',
      sourceScreen: prevScreen,
      rect: node.computedRect
    })
    return  // 跳过整棵子树
  }

  // 有变化，正常渲染
  for (const child of node.childNodes) {
    renderNodeToOutput(child, prevScreen)
  }
}
```

## 布局系统：终端里的 Flexbox

布局使用 **Yoga**（Meta 开源的跨平台 Flexbox 引擎），通过 WASM 绑定调用：

```typescript
// src/ink/layout/node.ts
type LayoutNode = {
  // 设置 Flexbox 属性
  setFlexDirection(direction)  // row | column | row-reverse | column-reverse
  setFlexGrow(n)
  setFlexShrink(n)
  setFlexBasis(value)
  setFlexWrap(wrap)
  setAlignItems(align)
  setJustifyContent(justify)
  setDisplay(display)           // flex | none
  setOverflow(overflow)         // visible | hidden | scroll
  setMargin/Padding/Border(edge, value)

  // 计算布局
  calculateLayout(width?, height?)

  // 读取计算结果
  getComputedLeft/Top/Width/Height()
}
```

组件中使用方式和 CSS Flexbox 几乎一样：

```tsx
// 水平排列，间距 1
<Box flexDirection="row" gap={1}>
  <Box width={20}>
    <Text>侧边栏</Text>
  </Box>
  <Box flexGrow={1}>
    <Text>主内容区（占满剩余空间）</Text>
  </Box>
</Box>
```

### 文本测量

文本节点有特殊的测量函数，告诉 Yoga 这段文本需要多大空间：

```typescript
// src/ink/dom.ts (lines 332-374)
function measureTextNode(node, width, widthMode) {
  // 1. 展开 Tab（每个 Tab 最多 8 个空格到下一个 Tab Stop）
  const expanded = expandTabs(text)

  // 2. 测量文本尺寸
  const measured = measureText(expanded)

  // 3. 如果超出宽度，执行换行
  if (measured.width > width) {
    const wrapped = wrapText(expanded, width)
    return measureText(wrapped)
  }

  return measured
}
```

## 焦点管理

```typescript
// src/ink/focus.ts
class FocusManager {
  activeElement: DOMElement | null   // 当前焦点元素
  focusStack: DOMElement[]           // 焦点栈（最多 32 层）

  // 设置焦点（自动 blur 上一个）
  focus(node) {
    if (this.activeElement) this.blur()
    this.activeElement = node
    this.focusStack.push(node)
    dispatch(node, new FocusEvent('focus'))
  }

  // Tab 键循环焦点
  focusNext(root) {
    const tabbable = collectTabbable(root)  // DFS 收集 tabIndex >= 0 的节点
    const currentIndex = tabbable.indexOf(this.activeElement)
    const next = tabbable[(currentIndex + 1) % tabbable.length]
    this.focus(next)
  }

  // 节点被移除时，从栈中恢复焦点
  handleNodeRemoved(node, root) {
    if (node === this.activeElement) {
      this.focusStack.pop()
      const prev = this.focusStack[this.focusStack.length - 1]
      if (prev) this.focus(prev)
    }
  }

  // 点击时设置焦点
  handleClickFocus(node) {
    if (node.attributes.tabIndex >= 0) {
      this.focus(node)
    }
  }
}
```

```
Tab 键焦点循环：

  ┌──────┐    Tab    ┌──────┐    Tab    ┌──────┐
  │按钮 A │ ────────▶ │按钮 B │ ────────▶ │按钮 C │
  └──────┘           └──────┘           └──────┘
      ▲                                      │
      │              Tab                     │
      └──────────────────────────────────────┘
```

## 事件系统：捕获 + 冒泡

和浏览器 DOM 事件一样，事件分**捕获阶段**和**冒泡阶段**：

```typescript
// src/ink/events/dispatcher.ts
class Dispatcher {
  dispatch(target, event) {
    // 1. 收集路径：target → root
    const path = collectPath(target)

    // 2. 捕获阶段（root → target）
    for (const node of path.reverse()) {
      const handler = node._eventHandlers?.['onCaptureKeyDown']
      if (handler) handler(event)
      if (event.stopped) return
    }

    // 3. 冒泡阶段（target → root）
    for (const node of path) {
      const handler = node._eventHandlers?.['onKeyDown']
      if (handler) handler(event)
      if (event.stopped) return
    }
  }
}
```

事件优先级（仿 React DOM）：

| 优先级 | 事件类型 | 说明 |
|--------|---------|------|
| Discrete | keyboard, click, focus, blur, paste | 同步处理，立即触发 re-render |
| Continuous | resize, scroll, mousemove | 可以合并，降低频率 |
| Default | 其他 | 正常优先级 |

## 全屏模式 vs 普通模式

```
普通模式（Main Screen）              全屏模式（Alt Screen）
─────────────────────              ─────────────────────
共享终端滚动历史                     独立的全屏画布
光标可以超出屏幕底部                  光标被限制在屏幕内
相对光标移动                         绝对光标定位 CSI H
无鼠标支持                           鼠标跟踪（mode 1003）
内容追加到 scrollback                退出时恢复原始屏幕
```

全屏模式由 `<AlternateScreen>` 组件触发：

```tsx
<AlternateScreen>
  {/* 这里面的所有内容都在全屏画布上渲染 */}
  <ScrollBox>
    <Messages />
  </ScrollBox>
  <PromptInput />
</AlternateScreen>
```

## 滚动的平滑处理

ScrollBox 的滚动不是一次性跳到目标位置，而是**分帧消耗**：

```typescript
// src/ink/ink.tsx (lines 757-759)
const SCROLL_MAX_PER_FRAME = 4  // 每帧最多滚动 4 行

// pendingScrollDelta 分多帧消耗
// 例如鼠标滚轮一次滚 12 行
// 帧 1: 消耗 4 行，剩余 8
// 帧 2: 消耗 4 行，剩余 4
// 帧 3: 消耗 4 行，剩余 0
```

这样做的好处是避免**一次滚轮事件触发一次全量重绘**。中间帧可以用 DECSTBM 硬件滚动，极低的传输成本（~50 字节 vs ~2000 字节）。

## 文本选择与搜索

引擎还实现了终端中的**文本选择**和**搜索高亮**：

```typescript
// src/ink/ink.tsx (lines 534-551)
// 选择：反转前景色和背景色
function applySelectionOverlay(screen, selection) {
  for (cell in selectionRange) {
    // 交换前景色和背景色
    cell.styleId = invertedStyleId
  }
}

// 搜索：高亮匹配文本
function applySearchHighlight(screen, matches) {
  for (cell in matchRange) {
    cell.styleId = highlightStyleId  // 黄底黑字
  }
}
```

这些叠加层在差量计算之前应用，所以它们和正常内容一样高效。

## 性能数据

| 优化项 | 效果 |
|--------|------|
| Cell 压缩（8 字节 vs 64+ 字节） | 内存减少 **8 倍** |
| 脏标记 + Blit 跳过 | 大部分帧只重绘 **<10%** 的 Cell |
| StylePool 转换缓存 | 热路径**零内存分配** |
| CharCache 跨帧缓存 | 大部分行**不需要重新 tokenize** |
| DECSTBM 硬件滚动 | 滚动操作从 ~2KB 降到 **~50 字节** |
| BigInt64Array.fill | 清屏一条指令，**O(1)** |
| 池重置（每 5 分钟） | 防止长会话**内存无限增长** |

## 小结

这个自研渲染引擎体现了**"在约束中做到极致"**的工程哲学：

1. **React 组件模型**：用熟悉的声明式 API 写终端 UI，但底层完全自定义
2. **Yoga Flexbox**：终端里也能用 Flexbox 布局，和 CSS 几乎一样的 API
3. **压缩 Cell 表示**：每个字符 8 字节，Int32 比较代替对象比较
4. **三级缓存**：CharPool + StylePool + HyperlinkPool，热路径零分配
5. **脏标记 + Blit**：没变的子树直接从前一帧复制，跳过整棵渲染
6. **DECSTBM 硬件滚动**：利用终端自身的滚动能力，传输量降 40 倍
7. **事件系统**：完整的捕获/冒泡，和浏览器 DOM 事件一致
8. **焦点管理**：Tab 循环、自动聚焦、栈式恢复

> **一个有趣的对比**：Chrome 浏览器的渲染引擎 Blink 有几百万行代码。这个终端渲染引擎只有 ~7000 行，但覆盖了布局、渲染、差量更新、事件、焦点、选择、搜索、滚动等完整功能。约束（终端只有字符 Cell）反而简化了很多问题。
