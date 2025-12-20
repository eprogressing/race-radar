import Foundation

struct Feed: Codable {
    let version: Int
    let updatedAt: String
    let items: [Competition]
    
    enum CodingKeys: String, CodingKey {
        case version, updatedAt, items
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        version = try container.decode(Int.self, forKey: .version)
        updatedAt = try container.decode(String.self, forKey: .updatedAt)
        // Lossy decoding: skip invalid items
        let lossyItems = try container.decode(LossyCodableArray<Competition>.self, forKey: .items)
        items = lossyItems.elements
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(version, forKey: .version)
        try container.encode(updatedAt, forKey: .updatedAt)
        try container.encode(items, forKey: .items)
    }
}

// Wrapper for decoding arrays while ignoring failed elements
struct LossyCodableArray<Element: Codable>: Decodable {
    let elements: [Element]
    
    private struct ElementWrapper: Decodable {
        var element: Element?
        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            element = try? container.decode(Element.self)
        }
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let wrappers = try container.decode([ElementWrapper].self)
        elements = wrappers.compactMap(\.element)
    }
}

struct Competition: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let bonusAmount: Int?
    let bonusText: String?
    let deadline: String?
    let category: [String]?
    let tags: [String]?
    let cover: String?
    let sourceName: String?
    let sourceUrl: String
    let summary: String?

    var deadlineDate: Date? {
        guard let deadline else { return nil }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.date(from: deadline)
    }
    
    // Robust Decoding
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        
        // Required fields (if missing, fail decode for this item, but Feed wrapper should handle it)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        sourceUrl = try container.decode(String.self, forKey: .sourceUrl)
        
        // Optional fields with defaults
        bonusAmount = try container.decodeIfPresent(Int.self, forKey: .bonusAmount) ?? 0
        bonusText = try container.decodeIfPresent(String.self, forKey: .bonusText) ?? "-"
        deadline = try container.decodeIfPresent(String.self, forKey: .deadline) ?? ""
        category = try container.decodeIfPresent([String].self, forKey: .category) ?? []
        tags = try container.decodeIfPresent([String].self, forKey: .tags) ?? []
        cover = try container.decodeIfPresent(String.self, forKey: .cover) ?? ""
        sourceName = try container.decodeIfPresent(String.self, forKey: .sourceName) ?? "Unknown"
        summary = try container.decodeIfPresent(String.self, forKey: .summary) ?? ""
    }
    
    // Default init for manual creation/previews
    init(id: String, title: String, bonusAmount: Int? = 0, bonusText: String? = "-", deadline: String? = "", category: [String]? = [], tags: [String]? = [], cover: String? = "", sourceName: String? = "Unknown", sourceUrl: String, summary: String? = "") {
        self.id = id
        self.title = title
        self.bonusAmount = bonusAmount
        self.bonusText = bonusText
        self.deadline = deadline
        self.category = category
        self.tags = tags
        self.cover = cover
        self.sourceName = sourceName
        self.sourceUrl = sourceUrl
        self.summary = summary
    }
}

// MARK: - Filter Models
enum SortOption: String, CaseIterable, Identifiable {
    case latest = "最新发布"
    case highBonus = "奖金最高"
    case soonestDeadline = "截止最近"
    
    var id: String { rawValue }
}

enum BonusTier: String, CaseIterable, Identifiable {
    case all = "不限"
    case k1 = "≥1000"
    case k5 = "≥5000"
    case k10 = "≥10000"
    
    var id: String { rawValue }
    
    var minAmount: Int {
        switch self {
        case .all: return 0
        case .k1: return 1_000
        case .k5: return 5_000
        case .k10: return 10_000
        }
    }
}

struct FilterState {
    var bonusTier: BonusTier = .all
    var onlyRecentDeadline: Bool = false
    var showHistory: Bool = false
    var selectedCategories: Set<String> = []
    var sortOption: SortOption = .latest
}

