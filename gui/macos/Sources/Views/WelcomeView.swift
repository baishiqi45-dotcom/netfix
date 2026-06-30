import SwiftUI

/// 首次启动欢迎页。
struct WelcomeView: View {
    var onStart: () -> Void
    var onSkip: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "network")
                .font(.system(size: 64))
                .foregroundStyle(.blue)

            VStack(spacing: 8) {
                Text("AI 开发工具断线急救")
                    .font(.title2)
                    .fontWeight(.semibold)
                    .multilineTextAlignment(.center)

                Text("Netfix 会检查 Wi-Fi、DNS、代理和目标服务，\n先告诉你哪里坏了，再给出可以直接点的处理动作。")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            VStack(spacing: 12) {
                Button("检查我的网络") {
                    onStart()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)

                Button("跳过介绍") {
                    onSkip()
                }
                .buttonStyle(.borderless)
            }
        }
        .padding(32)
        .frame(minWidth: 420, minHeight: 420)
    }
}
