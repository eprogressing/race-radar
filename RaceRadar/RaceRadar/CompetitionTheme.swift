import SwiftUI

enum CompetitionTheme {
    // Colors
    static let primaryBlue = Color.blue
    static let primaryPurple = Color.purple
    static let primaryGreen = Color.green
    static let primaryOrange = Color.orange
    static let textDark = Color.primary
    static let textLight = Color.secondary
    static let backgroundLight = Color.white
    static let backgroundDark = Color.black
    
    // Corner Radius
    static let cardRadius: CGFloat = 16
    static let pillRadius: CGFloat = 12
    static let smallRadius: CGFloat = 8
    
    // Spacing
    static let paddingSmall: CGFloat = 8
    static let paddingMedium: CGFloat = 12
    static let paddingLarge: CGFloat = 16
    static let paddingXLarge: CGFloat = 24
    
    // Category Colors
    static func color(for category: String?) -> Color {
        guard let category = category else { return .gray }
        if category.contains("编程") { return primaryBlue }
        if category.contains("数学建模") { return primaryPurple }
        if category.contains("AI") || category.contains("数据") { return primaryGreen }
        if category.contains("创业") || category.contains("创新") { return primaryOrange }
        return .gray
    }
    
    // Source Badge Colors
    static func badgeColor(for source: String?) -> Color {
        guard let source = source else { return .gray }
        if source.contains("赛氪") { return .indigo }
        if source.contains("Kaggle") { return .teal }
        if source.contains("52") || source.contains("竞赛") { return .pink }
        return .blue
    }
}
