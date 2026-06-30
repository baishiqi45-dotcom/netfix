import SwiftUI

/// 首次启动隐私披露：明确本地读取、日志保留和可选云端 AI 边界。
struct PrivacyDisclosureView: View {
    var onContinue: () -> Void
    var onSkip: () -> Void

    var body: some View {
        VStack(spacing: 22) {
            Spacer()

            Image(systemName: "hand.raised.fill")
                .font(.system(size: 54))
                .foregroundStyle(.blue)

            VStack(spacing: 8) {
                Text("先说明 netfix 会看什么")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("netfix 是本地优先的诊断工具。它不会内置节点，也不会替你购买住宅 IP。")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            VStack(alignment: .leading, spacing: 12) {
                disclosureRow("network", "读取本机网络状态", "网络代理设置、DNS、网关、本地监听端口、代理核心状态。")
                disclosureRow("doc.text.magnifyingglass", "保存本地报告和事件", "最近报告与事件日志保存在 ~/.netfix，可在设置里关闭或清理。")
                disclosureRow("sparkles", "云端 AI 默认关闭", "开启后先脱敏，再发送到你配置的 DeepSeek/Kimi/MiniMax/Qwen 等供应商。")
                disclosureRow("lock.shield", "修改前先问你", "会改系统网络设置的操作必须确认；应用代理前会先展示预览。")
            }
            .padding(.vertical, 4)

            Spacer()

            VStack(spacing: 12) {
                Button("我知道了，继续") {
                    onContinue()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)

                Button("跳过说明") {
                    onSkip()
                }
                .buttonStyle(.borderless)
            }
        }
        .padding(32)
        .frame(minWidth: 420, minHeight: 480)
    }

    private func disclosureRow(_ icon: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .foregroundStyle(.blue)
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.headline)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
