import SwiftUI
import Combine

/// 顶层视图路由：根据 onboarding 完成状态显示欢迎 / 权限 / 仪表盘。
struct RootView: View {
    @ObservedObject var backend: Backend
    @ObservedObject var healthMonitor: HealthMonitor
    @AppStorage("netfix.onboardingCompleted") private var onboardingCompleted = false
    @State private var onboardingStep = OnboardingStep.welcome

    var body: some View {
        Group {
            if onboardingCompleted {
                DashboardView(backend: backend, healthMonitor: healthMonitor)
            } else {
                switch onboardingStep {
                case .welcome:
                    WelcomeView(
                        onStart: { onboardingStep = .privacy },
                        onSkip: { onboardingStep = .privacy }
                    )
                case .privacy:
                    PrivacyDisclosureView(
                        onContinue: { onboardingStep = .permissions },
                        onSkip: { onboardingStep = .permissions }
                    )
                case .permissions:
                    OnboardingView(
                        onContinue: { onboardingStep = .proxySetup },
                        onSkip: { onboardingStep = .proxySetup }
                    )
                case .proxySetup:
                    ProxySetupView(
                        backend: backend,
                        onContinue: { completeOnboarding() },
                        onSkip: { completeOnboarding() }
                    )
                }
            }
        }
    }

    private func completeOnboarding() {
        onboardingCompleted = true
        onboardingStep = .welcome
    }
}

enum OnboardingStep {
    case welcome
    case privacy
    case permissions
    case proxySetup
}

// MARK: - App 入口

@main
struct NetfixApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        Settings {
            SettingsView(backend: appDelegate.backend)
        }
    }
}
