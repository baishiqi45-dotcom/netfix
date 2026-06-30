# Netfix 代理部署链路产品审计（2026-06-29）

> 范围：`gui/macos/Sources/Views/DashboardView.swift`、`SettingsView.swift`、`ProxySetupView.swift`、`AppDelegate.swift`、`netfix/residential_proxy.py`、相关测试。
> 视角：把 Netfix 当成**普通 macOS 用户**第一次拿到手上。目标用户不是工程师。
> 性质：专项审计。和 `PRODUCT_AUDIT_AND_ROADMAP_2026_06.md`（总报告）互补——那份覆盖启动、修复、错误条等全局问题；这份只攻**代理部署**这条主链路。
> 触发原因：用户强反馈 "部署代理界面完全看不懂 / 不知道复制什么 / 保存和部署有什么区别"。

---

## 0. 用户任务模型 vs 现在的产品模型

把用户真正要做的事摊开，再看现在 UI 的样子，差距一目了然。

**用户的心智模型（5 步）：**

```
1. 打开 App
2. 看到 "网络好像有问题" / "我想用代理"
3. 粘贴一行从服务商后台复制来的东西
4. 看到 "OK，部署好了"
5. 出问题时一键回到原状
```

**Netfix 现在的产品模型：**

```
打开 → 菜单栏 popover 460×620 → 6 张层卡（DNS 层 / 出口身份 / 路径/质量…）
     → 4 个 Tab（通用 / 服务 / AI / 代理 / 权限 / 关于）
     → 代理 Tab 第 4 个：粘贴框 + 预检 / 保存并检测 / 验证当前参数（3 个并列按钮）
     → "保存" ≠ "部署"（需要再点 "部署到这台 Mac"）
     → AI Tab 默认在第三个 Tab，蓝色主按钮，文案 "这是可选功能" 视觉上不像可选
```

**根因不是某条文案不好，而是信息架构和用户心智完全对不上。** 后面 12 个 P0 都是这个根因的具体表现。

---

## 1. P0 问题（按严重度排序）

### P0-1：代理部署被埋在 6 个 Tab 的第 4 个

**文件**：`SettingsView.swift:89-93`，`DashboardView.swift:430-439`，`AppDelegate.swift:105-108`

```swift
// SettingsView.swift
TabView {
    generalTab.tag("general")      // Tab 1
    servicesTab.tag("services")    // Tab 2
    aiTab.tag("ai")                // Tab 3
    proxyTab.tag("proxy")          // Tab 4 ← 核心功能
    permissionsTab.tag("permissions")
    aboutTab.tag("about")
}
```

**用户怎么误读**：用户的主任务是"部署代理"，但 App 把它和"通用""权限""关于"放在同一层级的设置 Tab 里。Dashboard 上那个叫"打开部署页"的按钮实际行为是 `showProxySettings()`——切到设置窗口的代理 Tab，但用户期望的是一个独立的、像新手引导一样的部署流程。

**替换方案**：

- Dashboard 卡片标题 `部署代理` → `让这台 Mac 用上你的代理`
- 副文案改为：`把你的代理服务商提供的整行连接信息粘贴进来，Netfix 会接管你 Mac 的网络流量，三步完成。`
- 主按钮 `打开部署页` → `开始部署代理`
- 副按钮 `我该复制什么？` → **删掉**（见 P0-2，主流程正文里直接说）
- 长远看：把"代理"从设置里拆出来，做成主屏核心区域，不再依赖跳设置

---

### P0-2：「我该复制什么？」这个按钮 = 产品自证失败

**文件**：`DashboardView.swift:440-444`

```swift
Button("我该复制什么？") {
    openProxySettings()  // 和"打开部署页"完全一样的动作
}
```

**用户怎么误读**：产品自己用按钮承认"用户不知道要复制什么"，但没在主流程告诉用户，而是塞一个二级按钮。更糟的是这个按钮和"打开部署页"功能完全一样——用户会以为这两个按钮去的是不同地方。

**替换方案（不要按钮，做成"提示卡"）**：

在粘贴框正上方放一张常驻提示卡（不是按钮、不是 DisclosureGroup）：

```
[ 粘贴你的代理连接 ]
去你的代理服务商后台（Bright Data / Oxylabs / 922S5 / IPIDEA 等）
→ 找到「代理生成」或「我的订阅」
→ 复制完整一行，例如：
   协议=socks5h，地址=代理服务器，端口=9000，用户名=<username>，密码=<password>
或服务商导出的 host,port,username,password 表格整段
⚠️ 不要复制出口 IP
[ 缩略图：一张服务商后台页面的灰度示意图 ]
```

现在代码里只有协议、地址、端口、用户名、密码这种工程字段说明（`SettingsView.swift:450`），是工程师写给工程师看的。

---

### P0-3：「保存」和「部署到这台 Mac」是两个按钮，但 99% 用户不知道这是两步

**文件**：`SettingsView.swift:454-474`（保存并检测 + 验证当前参数）和 `SettingsView.swift:905-910`（部署到这台 Mac）

```swift
// SettingsView.swift:454-474
HStack {
    Button { ... } label: { Label("预检", systemImage: "checklist") }
    Button { ... } label: { Label("保存并检测", systemImage: "bolt.heart") }  // 主按钮
        .buttonStyle(.borderedProminent)
    Button("验证当前参数") { ... }  // 第 3 个按钮，语义和"预检"重叠
}

// proxyProfileRow 内（SettingsView.swift:905+）
Button("部署到这台 Mac")  // 真正的"改网络设置"动作
Button("验证")
Button("启动监控")
Button("更新参数")
Button("删除")
```

**用户怎么误读**：用户点"保存并检测"——这名字听上去像"已经搞定"——然后关掉 App，浏览器还是直连。`proxySaveStatus` 文案自己写得很绕：`已保存并启动健康监控，但还没接管系统流量`（`ProxySetupView.swift:177`）。这句话出现在 UI 上时，用户已经走人了。

**替换方案**：

- 合并成一个 stepper 引导：`1 粘贴 → 2 预检 → 3 保存 → 4 部署到这台 Mac`，每步只能点"下一步"。
- "预检"在输入合法时直接变绿色 `✓ 已识别有效代理`。
- `保存并检测` 重命名为 `保存到这台 Mac`，并明确标注 `⚠️ 还没接管网络流量`。
- `部署到这台 Mac` 是唯一会改网络设置的按钮，放最显眼位置，前面带红色 `⚠️ 会要求管理员密码`。
- **删掉** `验证当前参数`——和"预检"语义重叠。

---

### P0-4：AI 卡片在首页和代理卡片并列，强烈暗示 AI 是必选

**文件**：`DashboardView.swift:455-494`

```swift
private var aiAssistantSection: some View {
    VStack(...) {
        HStack {
            Label("AI 看报告", systemImage: "sparkles")
            Spacer()
            Button("AI 设置") { ... }
        }
        Text("这是可选功能...")  // 写"可选"但视觉权重和代理并列
        HStack {
            Button { showAIQuestionSheet = true } label: {
                Label("让 AI 看报告", systemImage: "message")
            }
            .buttonStyle(.borderedProminent)  // ← 蓝色主按钮
        }
    }
}
```

**用户怎么误读**：首页三块业务卡：`AI 服务急救包` / `部署代理` / `AI 看报告`。前两块业务上并列，AI 跟代理平级。文字虽然写"这是可选功能"，但 `.borderedProminent` 蓝色主按钮的视觉权重把它顶到了最高优先级。

**替换方案**：

- 把 AI 整块从 DashboardView 主流程中**移除**。
- AI 只在两个地方出现：
  1. 诊断结果区下面一个 `看不太懂？让 AI 解释一下` 的 borderless 次要链接
  2. 设置 → AI 标签页（已经是这样）
- DashboardView 改成三块：`网络健康` / `部署代理` / `遇到问题怎么办`。第三块放 FAQ、撤销、退出。
- 行为级承诺：**不配 API Key 时，整个 App 100% 正常工作，没有任何 modal / banner 催用户去配 Key**。

---

### P0-5：「我没有代理服务商参数怎么办？」没有逃生口

**文件**：`ProxySetupView.swift:59-112`，`SettingsView.swift:419-481`

**用户怎么误读**：首页是空的、用户没买过任何代理服务、就是想"修一下我的网络"——粘贴框在等他输入，但他没有任何东西可以粘贴。`ProxySetupView` 顶部那段 `Text("未识别到常见代理客户端，你可以先跳过，稍后在设置里配置。")` 后面是空的，**没有任何引导**告诉他"如果你没有代理，先去诊断网络问题"。

**替换方案**：在 `ProxySetupView` 输入框上方加辅助区块：

```
第一次接触代理？
• 你的代理服务商是什么？Bright Data / Oxylabs / LunaProxy / 自建…
• 找服务商的「代理生成」或「我的订阅」页面
• 整段复制包含「主机、端口、用户名、密码」的那一行
   （带 http:// 或 socks5:// 开头的那一长串就是）
[ 查看图文教程 ]       ← 链接到帮助页
[ 我没有代理服务商 ]   ← 引导回首页做基础诊断
```

第二个按钮是关键：**把"没代理"这个用户场景当作主流程的一等公民**，而不是被忽略的边角。

---

### P0-6：状态卡片 6 个"层"是工程师分层概念，普通人看不懂

**文件**：`DashboardView.swift:170-177`

```swift
private let layerDefinitions: [(id: String, title: String, icon: String)] = [
    ("network", "本地网络", "wifi"),
    ("dns", "DNS 层", "globe"),
    ("proxy", "代理层", "network"),
    ("egress", "出口身份", "shield.lefthalf.filled"),
    ("path", "路径/质量", "arrow.left.arrow.right"),
    ("service", "目标服务", "server.rack"),
]
```

**用户怎么误读**：

- `DNS 层` → 用户：层是啥？
- `出口身份` → 用户：这是身份证吗？
- `路径/质量` → 用户：什么路径？
- `代理层` → 用户：层是啥？

**"层"是工程师词。** "出口身份"是技术词。普通 macOS 用户不读 OSI 模型。

**替换方案**：6 张合并成 3 张，全用人话：

| 旧（工程师） | 新（人话） |
|---|---|
| 本地网络 | **网络连接**（你 Wi-Fi 通不通） |
| DNS 层 + 路径/质量 | **上网速度**（能不能打开网站，快不快） |
| 代理层 + 出口身份 | **代理状态**（代理有没有在工作，别人看你来自哪里） |
| 目标服务 | **目标网站**（你想上的那个能不能上） |

或者更进一步：去掉 6 张卡，做成一句大状态 + 详情展开：

```
[ ● ] 你的网络有点问题
     代理：已配置但未生效 · 目标网站：2/3 能上
     [ 看详情 ]   [ 让 Netfix 处理 ]
```

---

### P0-7：「引擎」是产品自造词

**文件**：散落多处

- `DashboardView.swift:1020` → `headline = "正在启动引擎…"`
- `DashboardView.swift:1067` → `headline = "引擎就绪"`
- `SettingsView.swift:355` → `bridgeStatusMenuItem.title = "桥接状态：本地引擎未就绪"`
- `SettingsView.swift:770` → `aiStatus = "引擎启动后可配置 AI 和代理。"`
- `AppDelegate.swift:91` → `window.title = "Netfix 设置"`（OK，这里是设置，但代码里其他位置都用"引擎"指代 Netfix 自己）

**用户怎么误读**：Mac 用户认知里没有"引擎"——这是 Chrome / Edge 那种 App 自己的内部组件名。**用户不需要知道 Netfix 内部有"引擎"这层抽象**。最危险的是 `本地引擎未就绪`——用户搞不清"引擎"和"App"是不是一回事。

**替换方案**：

| 旧 | 新 |
|---|---|
| 正在启动引擎… | 正在准备… |
| 引擎就绪 | 就绪，可以开始 |
| 本地引擎未就绪 | Netfix 还没准备好，稍等几秒再试 |
| 引擎启动后可配置 AI 和代理 | 启动完成后可配置 AI 和代理 |
| 引擎返回后显示… | 准备就绪后这里会显示… |

`codex._request_http_proxy` / `proxy_bridge.start_http_bridge` 这种内部函数名无所谓，但凡是会显示给用户的字符串，都不应该出现"引擎"。

---

### P0-8：Popover 460×620 装不下 6 张卡 + 8 个按钮 + 3 个分区

**文件**：`DashboardView.swift:59`，`:759-815`

```swift
.frame(minWidth: 420, idealWidth: 460, minHeight: 520)
```

底部工具栏（`DashboardView.swift:759-815`）：

```swift
Button("一键诊断")  Button("一键修复")  Button("撤销")
Toggle("自动修复")
Button("控制台")  Button("部署代理")  Button("日志")  Button("设置")
```

**用户怎么误读**：460px 宽的菜单栏气泡里塞 8 个控件 + 6 张状态卡 + AI 入口 + 急救包 + 进度 + 错误 + 结果。**视觉上根本找不到主按钮在哪**。更糟的是：

- `一键诊断` 和 `一键修复` 视觉权重相同，但前者只读、后者会改设置——两个完全不同的安全级别
- 菜单栏 popover 是 `.transient` 行为（`AppDelegate.swift:71`），点外面就关——用户填了一半表单点别处就丢了

**替换方案**：

- 菜单栏 popover 减到只显示：**状态点 + 4 个一级操作**（诊断网络 / 部署代理 / 撤销上次 / 看 AI 报告——AI 用次要按钮）
- 详情展开到主窗口 800×600，**不再是 popover**
- 状态卡 6 张合并成 3 张（见 P0-6）
- 底部 8 个按钮减到 3 个：`诊断` / `部署` / `撤销`
- 长任务表单（粘贴、设置）必须在主窗口里完成

---

### P0-9：「诊断 / 修复 / 撤销」三按钮的破坏性边界完全没标

**文件**：`DashboardView.swift:761-781`

```swift
Button("一键诊断")   // 蓝色主按钮
Button("一键修复")   // 蓝色边框
Button("撤销")       // borderless
```

**用户怎么误读**：用户跑完诊断看到"一键修复"就点了——这按钮在 `explanationCard` 里会调 `explanation.primaryAction`（`DashboardView.swift:557-567`），可能调用 `executeAction`，**macOS 会弹管理员授权**。卡片上只显示一个蓝色按钮，没有"⚠️ 会要求输入密码"的提示。`showConfirmation` 文案 `让 Netfix 处理这个问题？将处理「\(action.label)」。如果这一步会改网络设置，macOS 会弹出管理员授权`（`DashboardView.swift:75`）——文字过软。

**替换方案**：

- 任何会调 `networksetup` 或写 Keychain 的按钮，统一加前缀 `⚠️ 会要求管理员密码：`。
- 主按钮根据 `action.needsConfirm` 区分：低风险叫 `立即处理`，高风险叫 `处理（会改网络设置）`。
- 任何可撤销的破坏性操作完成后，**自动**在状态头插入一行 `刚才你改了 X，要不要撤销？`（24 小时内可撤销），不是让用户去工具栏找"撤销"按钮。
- `撤销` 按钮（`DashboardView.swift:777`）在 `healthMonitor.lastReport != nil` 时始终显示，不要 `borderless`，给它一个有边框的样式。

---

### P0-10：「已保存的代理」放在粘贴框下面，违反主流程预期

**文件**：`SettingsView.swift:419-526`

```swift
Section { ... }  // 粘贴框 + 三个按钮
Section("结果和下一步") { ... }
Section("已保存的代理") { ... }   // ← 在粘贴框正下方
Section("健康维护") { ... }
Section { DisclosureGroup("更多：导出、恢复网络设置") { ... } }
```

**用户怎么误读**：用户以为"已保存的代理"是"历史记录"，但实际任务是"我有一行新的，粘贴 → 保存 → 用它"。**已保存代理区应该和"粘贴 → 预检 → 部署"是同一视觉流程**，不能和"健康监控""更多选项"挤在一列。

更糟的是 `Section("已保存的代理")` 里每行又有 6 个按钮（部署 / 验证 / 启动监控 / 更新参数 / 删除 / 导出配置包 / 给终端工具使用），用户根本分不清。

**替换方案**：

- 代理 Tab 顶部固定一行 stepper：`1 粘贴  →  2 预检  →  3 保存  →  4 部署到这台 Mac`
- "已保存的代理"区只展示 3 个元素：图标 + 名称 + 状态徽标（`已部署` / `未部署` / `健康` / `异常`）
- 单条操作放二级页：点代理行 → 进入 `代理详情`，里面再放 6 个按钮
- 健康维护、导出、恢复、桥接状态，全部进 `高级` DisclosureGroup

---

### P0-11：菜单栏 App + popover 形态本身不适合做"重活"

**文件**：`AppDelegate.swift:21-32, 67-77`

```swift
NSApp.setActivationPolicy(.regular)  // ← 是的，是 regular（有 Dock 图标）
popover.contentSize = NSSize(width: 460, height: 620)
popover.behavior = .transient        // ← 点击外部就关
```

**用户怎么误读**：

- `setActivationPolicy(.regular)` 让它有 Dock 图标——但 popover 是 `.transient` 行为，**用户点别处窗口就消失**
- 状态是"菜单栏 App"——很多用户不点菜单栏图标，或者根本不知道这是个 App
- popover 高度 620 像素，超过很多 MacBook 屏幕顶部空间，**会被截断**

**替换方案**：

- 既然已经是 `.regular`，就做正经 App：**主窗口固定可关闭但保留 Dock**。
- 菜单栏图标只放一个状态灯和"打开主窗口"快捷入口。
- 不要 popover。
- 主窗口最少 720×520 才能装下 6 个分区 + 状态卡 + 流程引导。

---

### P0-12：「控制台」是开发者入口，不该给普通用户

**文件**：`DashboardView.swift:789-793`

```swift
Button("控制台") {
    openLocalConsole()  // 打开 backend API URL
}
```

`openLocalConsole` 行为（`DashboardView.swift:402-405`）：

```swift
private func openLocalConsole() {
    guard let url = backend.apiURL else { return }
    NSWorkspace.shared.open(url)  // 浏览器打开 127.0.0.1:xxx
}
```

**用户怎么误读**：普通用户点了"控制台"，浏览器打开一个全英文 JSON API 页面——用户不知道这是啥，会以为是 bug 然后去搜"Netfix 控制台打不开"。

**替换方案**：

- 删掉 DashboardView 底部工具栏的 `控制台` 按钮。
- 移到 `设置` → `高级` 折叠区，叫 `开发者：打开本地 API`。

---

## 2. 推荐信息架构

### 2.1 顶层导航（4 个区，不超过 4 个）

```
┌─ Netfix 主窗口（独立 App，不是 popover；最小 720×520）──────────┐
│                                                                   │
│  ① 网络健康                                                       │
│     - 大状态点 + 一句话：网络正常 / 有问题 / 已部署代理         │
│     - 三张卡：网络连接 / 代理状态 / 目标网站                      │
│     - 主按钮：诊断（低风险，蓝主按钮）                            │
│                                                                   │
│  ② 部署代理                                                       │
│     - 顶部 stepper：1 粘贴 → 2 预检 → 3 保存 → 4 部署           │
│     - 提示卡（常驻，非折叠）：                                    │
│        "去服务商后台复制整行：协议、地址、端口、用户名、密码"    │
│     - 大输入框 + 实时识别：✓ 有效 / ✗ 缺端口                     │
│     - 主按钮链：预检（灰）→ 保存（灰）→ 部署到这台 Mac（蓝）    │
│     - 副按钮：[ 我没有代理服务商 ]                               │
│                                                                   │
│  ③ 已保存的代理                                                   │
│     - 列表：图标 + 名称 + 状态徽标（已部署/未部署/健康/异常）   │
│     - 单条点开进入详情页：验证 / 部署 / 撤销 / 删除              │
│                                                                   │
│  ④ 遇到问题                                                       │
│     - 撤销上次修改（一级 CTA）                                   │
│     - 看不懂诊断？看 AI 解释（borderless 次要链接）              │
│     - 常见问题 / 联系支持                                        │
│                                                                   │
│  [ ⚙ 设置 ]  [ 📋 日志 ]                ← 右上角次要入口        │
└───────────────────────────────────────────────────────────────────┘
```

### 2.2 设置窗口（独立，5 个 Tab）

```
通用        开机启动、通知、菜单栏图标
AI          独立 Tab，承认它是单独子系统；显式标注"可选"
代理高级    检测目标矩阵、健康监控间隔、导出、桥接自动恢复
隐私        日志保留、清理本地数据、删除全部
关于        版本、致谢、退出
```

注意：把"代理"主流程从设置里拿走后，**设置里的 `代理` Tab 重命名为 `代理高级`**，避免和主屏冲突。

### 2.3 关键交互（每个都要遵守）

- **AI 永远不在主流程上抢视觉权重**。它要么是 `.borderless` 链接，要么藏在设置里。
- **任何会改网络设置的按钮**，前缀加 `⚠️ 会要求管理员密码`，主按钮蓝色 + 边框。
- **任何会写 Keychain 的按钮**，后置一行 `密码只存本机密码库，不进日志`。
- **破坏性操作完成后**，自动在状态头插入 `刚才你改了 X，24 小时内可撤销`，而不是让用户去工具栏翻"撤销"。
- **新流程的状态反馈永远用动词 + 现在时**，不要用 `已保存，下一步…` 这种倒装。

---

## 3. 5 条验收标准

普通用户做到这 5 条，产品才算"可用"。任何一条没做到，发版即返工。

### AC-1：5 分钟零指导能完成首次部署

给一个从未用过 Netfix、没看过文档的 macOS 普通用户一个 proxy provider 的 socks5h 凭据，他**不读任何说明**也能在 5 分钟内：

- 打开 App（不是 popover，是独立窗口）
- 在第一屏看到"部署代理"和具体步骤
- 找到正确字段、正确粘贴（不会去复制出口 IP）
- 看到"已部署"的明确状态——不是 `已保存，密码已写入本机密码库，下一步可点部署` 这种话

### AC-2：「我应该复制什么？」的按钮被删掉

- 粘贴框上方常驻"提示卡"用图 + 一段话告诉用户"去服务商后台的'代理生成'页面，复制整行"。
- 服务商后台的截图 / mockup 一直可见。
- `出口 IP 不能用` 写在最显眼位置。
- `DashboardView.swift:440-444` 的 `我该复制什么？` Button 整段删掉。

### AC-3：「保存」和「部署」是两个绝对清楚的两步

- "保存"按钮叫 `保存到这台 Mac`，副文案 `还没接管网络流量`。
- "部署"按钮叫 `部署到这台 Mac`，前面 `⚠️ 会要求管理员密码`，是蓝色主按钮。
- 已部署的代理在主列表显示绿色徽标 `已部署`。
- 已保存未部署的代理显示灰色徽标 `未部署`，并提供一键部署按钮。
- `SettingsView.swift:470` 的 `Button("验证当前参数")` 整段删掉。

### AC-4：状态卡和错误信息全是中文人话

- 没有任何 `引擎` / `层` / `路径/质量` / `出口身份` / `credential_ref` 这种工程师词出现在面向用户的字符串里。
- 错误条说 `代理失效了，要不要恢复？` 而不是 `bridge_stale_bridge: recovery_available=true`。
- `撤销` 按钮在已部署状态下**默认可见**（绿色边框），不需要点"高级"折叠。
- 6 张层卡合并成 3 张：网络连接 / 代理状态 / 目标网站（详见 P0-6）。

### AC-5：AI 存在感不高于"诊断结果下方的'看不太懂？让 AI 解释'"

- DashboardView 的 `aiAssistantSection` 主卡片（`DashboardView.swift:455-494`）整段删除。
- AI 只在诊断结果卡最下方有一个 `.borderless` 链接。
- 设置里 `AI` Tab 标注 `可选：需要 AI 解释诊断时再开`。
- 没配 API Key 时，**整个 App 所有功能（诊断 / 部署 / 恢复）100% 正常工作**，没有任何 modal / banner / 状态灯变红 / 按钮置灰催用户去配 Key。
- 自动跑一遍 `bin/network-triage.sh` 等价行为：把 AI 整个 disable 也不影响 ① 诊断 ② 修复 ③ 部署 ④ 撤销。

---

## 4. 不在这次范围内、但建议下一轮审计

- 启动链路：5 秒内是否能让用户看到第一屏（`Backend.swift`、AppDelegate `applicationDidFinishLaunching`）
- 诊断报告的可读性：6 张卡合并后，详情页是否能讲人话
- AI 解释的产品化质量：让 AI 解释报告这个动作本身是不是真的有用
- 错误条的统一产品语言：`friendlyErrorMessage` 散落多处
- 国际化：现在全是中文字符串，没看到 `.strings` 文件

---

## 5. 落地建议（动哪些文件）

按修改成本排序：

| 优先级 | 文件 | 改动 | 估时 |
|---|---|---|---|
| **P0-4** | `DashboardView.swift:455-494` | 删 `aiAssistantSection` | 30 分钟 |
| **P0-12** | `DashboardView.swift:789-793` | 删 `控制台` 按钮，挪到设置高级 | 15 分钟 |
| **P0-2** | `DashboardView.swift:440-444` + `SettingsView.swift:441-447` | 删 `我该复制什么？` 按钮，改成常驻提示卡 | 2 小时 |
| **P0-5** | `ProxySetupView.swift:59-112` | 加"我没有代理服务商"次按钮 | 1 小时 |
| **P0-7** | 全局搜 `引擎` 替换 | 字符串替换 | 1 小时 |
| **P0-6** | `DashboardView.swift:170-177, 179-185` | 6 张卡合并成 3 张 + 改文案 | 半天 |
| **P0-3** | `SettingsView.swift:454-474, 905-910` | stepper 引导 + 删 `验证当前参数` | 1 天 |
| **P0-9** | `DashboardView.swift:761-781, 557-567` | 按钮加破坏性边界提示 + 自动撤销提示 | 半天 |
| **P0-10** | `SettingsView.swift:419-526` | 重排 Tab 顺序 + 步骤 stepper | 1 天 |
| **P0-1** | `SettingsView.swift:89-93` + `DashboardView.swift:411-453` | 代理从设置第 4 Tab 提升到主屏核心区 | 2 天 |
| **P0-8 / P0-11** | `AppDelegate.swift:67-77` | popover 改成主窗口 | 2 天 |

整体估算：P0-2 / P0-4 / P0-5 / P0-7 / P0-12 五个加在一起是**半天**的活，能把最刺眼的 5 个问题灭掉，可以作为 v0.3 的 hotfix 单独发。剩下 6 个需要产品 / 设计参与排期。

---

## 6. 附录：测试覆盖度对照

`tests/test_macos_proxy_export_ui.py` 和 `tests/test_macos_onboarding.py` 主要用**字符串存在性断言**（`assert "xxx" in settings`）来锁结构，没有真正的端到端覆盖：

- `test_macos_proxy_deployment_decision_is_decoded_and_rendered` 验证 `proxyDeploymentDecisionBlock` 存在，**没有验证它对普通用户可读**
- `test_proxy_setup_exposes_one_paste_proxy_onboarding_path` 验证 `有供应商给你的代理参数？直接粘贴` 字符串存在，**没有验证用户能否真的走通**

**测试侧建议补**（不在本次范围）：

- Snapshot 测试代理 Tab 截图，比对文案是否含工程师词
- 验收清单脚本：把本文 §3 的 5 条 AC 写成 `test_proxy_deploy_acceptance.py`，每跑一次 grep 一遍面向用户字符串
- e2e：用 Playwright/Selenium 跑粘贴 → 部署 → 撤销，但 macOS App 暂时跑不了，需要 XCUITest 单独写

---

> 这次审计的责任边界：纯产品 / UX 视角，不动后端逻辑。`netfix/residential_proxy.py` 的 500+ 行后端代码（解析、部署、回滚、桥接）功能上是齐全的，问题在前端**怎么把它呈现给用户**。
>
> 下一个动作建议：从 P0-4（删 AI 主卡片）+ P0-2（删按钮改提示卡）+ P0-12（删控制台按钮）三个半小时活开始，做 v0.3 hotfix。
