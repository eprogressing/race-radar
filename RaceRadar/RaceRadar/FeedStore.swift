import Foundation

@MainActor
final class FeedStore: ObservableObject {
    @Published var items: [Competition] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var updatedAt: String = "-"

    private let cacheFileName = "feed_cache.json"

    func load() async {
        // 先读缓存（秒开）
        if let (cachedItems, cachedTime) = loadCache() {
            self.items = cachedItems
            self.updatedAt = cachedTime
        }
        // 再拉网络（更新）
        await refresh()
    }
    
    func refresh() async {
        await fetch(ignoringCache: false)
    }
    
    func reloadIgnoringCache() async {
        items = [] // Clear current items to show loading state
        await fetch(ignoringCache: true)
    }
    
    private func fetch(ignoringCache: Bool) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            var url = Constants.feedURL
            if ignoringCache {
                // Add cache busting
                if var comps = URLComponents(url: url, resolvingAgainstBaseURL: true) {
                    comps.queryItems = [URLQueryItem(name: "t", value: "\(Date().timeIntervalSince1970)")]
                    if let newUrl = comps.url { url = newUrl }
                }
            }
            
            var req = URLRequest(url: url)
            req.cachePolicy = .reloadIgnoringLocalCacheData
            req.timeoutInterval = 15

            let (data, _) = try await URLSession.shared.data(for: req)
            let feed = try JSONDecoder().decode(Feed.self, from: data)
            
            // Robust check: filter out potentially broken items if decoding succeeded but produced weird data
            // (Though our custom decoder handles most cases)
            
            // Deduplicate items based on ID
            var uniqueItems = [Competition]()
            var seenIds = Set<String>()
            var duplicatesCount = 0
            
            for item in feed.items {
                if !seenIds.contains(item.id) {
                    seenIds.insert(item.id)
                    uniqueItems.append(item)
                } else {
                    duplicatesCount += 1
                }
            }
            
            if duplicatesCount > 0 {
                print("⚠️ Removed \(duplicatesCount) duplicate items from feed.")
            }
            
            self.items = uniqueItems
            self.updatedAt = feed.updatedAt
            saveCache(data)
        } catch {
            print("Feed error: \(error)")
            if items.isEmpty {
                errorMessage = "加载失败：请检查网络或 feed.json 地址"
            } else {
                errorMessage = "网络刷新失败，已显示本地缓存"
            }
        }
    }

    private func cacheURL() -> URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(cacheFileName)
    }

    private func saveCache(_ data: Data) {
        try? data.write(to: cacheURL(), options: .atomic)
    }

    private func loadCache() -> ([Competition], String)? {
        guard let data = try? Data(contentsOf: cacheURL()),
              let feed = try? JSONDecoder().decode(Feed.self, from: data) else { return nil }
        var seen = Set<String>()
        var uniq: [Competition] = []
        for item in feed.items {
            if !seen.contains(item.id) {
                seen.insert(item.id)
                uniq.append(item)
            }
        }
        return (uniq, feed.updatedAt)
    }
}
