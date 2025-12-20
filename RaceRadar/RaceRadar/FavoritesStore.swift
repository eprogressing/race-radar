import Foundation
import SwiftUI

@MainActor
final class FavoritesStore: ObservableObject {
    private let key = "favorite_ids"
    @Published private(set) var ids: Set<String> = []

    init() {
        if let data = UserDefaults.standard.data(forKey: key),
           let saved = try? JSONDecoder().decode([String].self, from: data) {
            self.ids = Set(saved)
        }
    }

    func toggle(_ id: String) {
        objectWillChange.send()
        if ids.contains(id) {
            ids.remove(id)
        } else {
            ids.insert(id)
        }
        save()
    }

    func contains(_ id: String) -> Bool {
        ids.contains(id)
    }

    private func save() {
        if let data = try? JSONEncoder().encode(Array(ids)) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}
