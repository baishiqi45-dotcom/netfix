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
                Text("网络出问题了？我帮你看看")
                    .font(.title2)
                    .fontWeight(.semibold)
                    .multilineTextAlignment(.center)

                Text("Netfix 会看你的网络，告诉你哪里坏了、怎么修。\n有代理账号时，也可以直接粘贴，让这台 Mac 用它上网。")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            VStack(spacing: 12) {
                Button("开始看我的网络") {
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
