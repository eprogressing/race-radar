import SwiftUI

@main
struct RaceRadarApp: App {
    @StateObject private var feedStore = FeedStore()
    @StateObject private var favStore = FavoritesStore()
    
    var body: some Scene {
        WindowGroup {
            RootTabs()
                .environmentObject(feedStore)
                .environmentObject(favStore)
        }
    }
}
