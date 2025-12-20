import SwiftUI

struct PosterView: View {
    let competition: Competition
    let qrImage: UIImage?

    var body: some View {
        ZStack {
            Color.white

            VStack(alignment: .leading, spacing: 28) {
                // 标题
                Text(competition.title)
                    .font(.system(size: 46, weight: .semibold))
                    .foregroundStyle(.black)
                    .lineLimit(3)

                // 来源
                Text("来源：\(competition.sourceName ?? "未知")")
                    .font(.system(size: 22, weight: .medium))
                    .foregroundStyle(.gray)

                // 奖金
                Text(bonusLine)
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle((competition.bonusAmount ?? 0) > 0 ? .red : .gray)

                // 截止信息
                Text(deadlineLine)
                    .font(.system(size: 22, weight: .medium))
                    .foregroundStyle(.black.opacity(0.75))

                Spacer()

                HStack(alignment: .center, spacing: 18) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("扫码直达报名 / 详情")
                            .font(.system(size: 22, weight: .semibold))
                            .foregroundStyle(.black)

                        Text(competition.sourceUrl)
                            .font(.system(size: 16))
                            .foregroundStyle(.gray)
                            .lineLimit(2)
                    }

                    Spacer()

                    if let qrImage {
                        Image(uiImage: qrImage)
                            .interpolation(.none)
                            .resizable()
                            .frame(width: 260, height: 260)
                    } else {
                        RoundedRectangle(cornerRadius: 18)
                            .stroke(.gray, lineWidth: 2)
                            .frame(width: 260, height: 260)
                            .overlay(Text("QR\nN/A").foregroundStyle(.gray))
                    }
                }
            }
            .padding(72)
        }
        .clipped()
    }

    private var bonusLine: String {
        if let amount = competition.bonusAmount, amount > 0, let text = competition.bonusText, text != "-" {
            return "奖金：\(text)"
        }
        return "奖金：-"
    }

    private var deadlineLine: String {
        guard let d = competition.deadline?.trimmingCharacters(in: .whitespacesAndNewlines), !d.isEmpty else {
            return "截止：待公布"
        }
        return "截止：\(d)"
    }
}
