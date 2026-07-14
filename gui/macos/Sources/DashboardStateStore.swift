import Combine
import Foundation

@MainActor
final class DashboardStateStore: ObservableObject {
    typealias Loader = () async throws -> DashboardStateResponse

    @Published private(set) var state: DashboardStateResponse?
    @Published private(set) var isRefreshing = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var lastUpdated: Date?

    private var loader: Loader?
    private var refreshTask: Task<DashboardStateResponse, Error>?
    private var refreshID: UUID?

    init(loader: Loader? = nil) {
        self.loader = loader
    }

    func configure(client: APIClient) {
        loader = { try await client.dashboardState() }
    }

    func clearClient() {
        loader = nil
        refreshTask?.cancel()
        refreshTask = nil
        refreshID = nil
        isRefreshing = false
    }

    func refresh() async {
        guard let loader else {
            errorMessage = "Netfix 还没准备好。"
            return
        }

        if let refreshTask, let refreshID {
            await finish(refreshTask, id: refreshID)
            return
        }

        isRefreshing = true
        let id = UUID()
        let task = Task { try await loader() }
        refreshTask = task
        refreshID = id
        await finish(task, id: id)
    }

    private func finish(_ task: Task<DashboardStateResponse, Error>, id: UUID) async {
        do {
            let response = try await task.value
            if refreshID == id {
                state = response
                errorMessage = nil
                lastUpdated = Date()
            }
        } catch is CancellationError {
            // A backend restart cancels the old request. The new client will
            // trigger a fresh read when it becomes ready.
        } catch {
            if refreshID == id {
                errorMessage = "暂时读不到当前网络状态。"
            }
        }
        if refreshID == id {
            refreshTask = nil
            refreshID = nil
            isRefreshing = false
        }
    }
}
