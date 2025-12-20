import SwiftUI

struct SourceBadgeView: View {
    let sourceName: String?
    
    var body: some View {
        Text(displayName)
            .font(.system(size: 10, weight: .bold))
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(CompetitionTheme.badgeColor(for: sourceName).opacity(0.1))
            .foregroundStyle(CompetitionTheme.badgeColor(for: sourceName))
            .clipShape(Capsule())
    }
    
    private var displayName: String {
        guard let name = sourceName else { return "未知" }
        if name.contains("赛氪") { return "赛氪" }
        if name.contains("Kaggle") { return "Kaggle" }
        if name.contains("52") || name.contains("竞赛网") { return "52竞赛" }
        return String(name.prefix(6))
    }
}

struct CategoryStripe: View {
    let category: String?
    
    var body: some View {
        Rectangle()
            .fill(CompetitionTheme.color(for: category))
            .frame(width: 4)
    }
}

struct PrizeView: View {
    let amount: Int?
    let text: String?
    
    var body: some View {
        VStack(alignment: .trailing, spacing: 2) {
            if let amount = amount, amount > 0 {
                Text(formattedAmount(amount))
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(.red)
                if let text = text, !text.isEmpty, text != "-" {
                    Text(text)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            } else {
                Text("—")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(.secondary)
            }
        }
    }
    
    private func formattedAmount(_ amount: Int) -> String {
        if amount >= 10000 {
            let wan = Double(amount) / 10000.0
            return String(format: "¥%.1f万", wan).replacingOccurrences(of: ".0", with: "")
        }
        return "¥\(amount)"
    }
}

struct DeadlinePillView: View {
    let deadlineDate: Date?
    
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "clock")
                .font(.system(size: 10))
            Text(deadlineText)
                .font(.system(size: 11, weight: .semibold))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(pillColor.opacity(0.1))
        .foregroundStyle(pillColor)
        .clipShape(Capsule())
    }
    
    private var daysRemaining: Int {
        guard let date = deadlineDate else { return -999 }
        // Use startOfDay to ensure consistent day comparison
        let calendar = Calendar.current
        let nowStart = calendar.startOfDay(for: Date())
        let deadlineStart = calendar.startOfDay(for: date)
        
        return calendar.dateComponents([.day], from: nowStart, to: deadlineStart).day ?? -999
    }
    
    private var deadlineText: String {
        guard let _ = deadlineDate else { return "待定" }
        if daysRemaining < 0 { return "已截止" }
        if daysRemaining == 0 { return "今天截止" }
        if daysRemaining <= 7 { return "\(daysRemaining)天后截止" }
        let formatter = DateFormatter()
        formatter.dateFormat = "MM-dd截止"
        return formatter.string(from: deadlineDate!)
    }
    
    private var pillColor: Color {
        guard let _ = deadlineDate else { return .gray }
        if daysRemaining < 0 { return .gray }
        if daysRemaining <= 3 { return .red }
        if daysRemaining <= 7 { return .orange }
        return .green
    }
}
