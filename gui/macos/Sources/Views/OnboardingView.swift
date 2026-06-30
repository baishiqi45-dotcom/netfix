import SwiftUI

/// 权限说明页，解释为什么需要本地网络权限。
struct OnboardingView: View {
    var onContinue: () -> Void
    var onSkip: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "lock.shield")
                .font(.system(size: 56))
                .foregroundStyle(.blue)

            VStack(spacing: 10) {
                Text("允许访问本地网络")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("netfix 需要检测你的网关、DNS、本地代理端口和局域网连接状态。\n默认只保存在本机；云端 AI 解释需要你在设置里主动开启。")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.circle")
                        .foregroundStyle(.green)
                    Text("检测 Wi-Fi 与网关是否可达")
                }
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.circle")
                        .foregroundStyle(.green)
                    Text("检查 DNS 解析是否正常")
                }
                HStack(spacing: 10) {
                    Image(systemName: "checkmark.circle")
                        .foregroundStyle(.green)
                    Text("判断代理节点是否可用")
                }
            }
            .font(.callout)
            .padding(.vertical, 8)

            Spacer()

            VStack(spacing: 12) {
                Button("我已授权，继续") {
                    onContinue()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)

                Button("打开系统设置") {
                    openLocalNetworkSettings()
                }
                .buttonStyle(.bordered)
                .controlSize(.large)

                Button("跳过，使用有限检测") {
                    onSkip()
                }
                .buttonStyle(.borderless)
            }
        }
        .padding(32)
        .frame(minWidth: 420, minHeight: 420)
    }

    /// 打开「系统设置 → 隐私与安全性 → 本地网络」。
    private func openLocalNetworkSettings() {
        let urlString = "x-apple.systempreferences:com.apple.preference.security?Privacy_LocalNetwork"
        if let url = URL(string: urlString) {
            NSWorkspace.shared.open(url)
        }
    }
}

