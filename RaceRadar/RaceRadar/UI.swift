import SwiftUI
import CoreImage.CIFilterBuiltins

// MARK: - Components
struct ShimmerView: View {
    @State private var phase: CGFloat = 0
    
    var body: some View {
        GeometryReader { geo in
            Rectangle()
                .fill(
                    LinearGradient(
                        gradient: Gradient(colors: [.gray.opacity(0.1), .gray.opacity(0.3), .gray.opacity(0.1)]),
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .mask(Rectangle().fill(
                    LinearGradient(
                        gradient: Gradient(colors: [.clear, .black, .clear]),
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                ))
                .offset(x: -geo.size.width + phase * 2 * geo.size.width)
                .onAppear {
                    withAnimation(.linear(duration: 1.5).repeatForever(autoreverses: false)) {
                        phase = 1
                    }
                }
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

struct SkeletonCard: View {
    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.gray.opacity(0.1))
                .frame(width: 72, height: 72)
                .overlay(ShimmerView())
            
            VStack(alignment: .leading, spacing: 10) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.gray.opacity(0.1))
                    .frame(height: 20)
                    .frame(maxWidth: .infinity)
                    .overlay(ShimmerView())
                
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.gray.opacity(0.1))
                    .frame(width: 120, height: 16)
                    .overlay(ShimmerView())
                
                HStack {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.gray.opacity(0.1))
                        .frame(width: 60, height: 24)
                        .overlay(ShimmerView())
                    Spacer()
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.gray.opacity(0.1))
                        .frame(width: 80, height: 24)
                        .overlay(ShimmerView())
                }
            }
        }
        .padding(12)
        .background(.white)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
    }
}

struct QRCodeView: View {
    let url: String
    
    var body: some View {
        if let cgImage = generateQRCode(from: url) {
            Image(uiImage: UIImage(cgImage: cgImage))
                .interpolation(.none)
                .resizable()
                .scaledToFit()
        } else {
            Color.gray
        }
    }
    
    private func generateQRCode(from string: String) -> CGImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        
        if let outputImage = filter.outputImage {
            return context.createCGImage(outputImage, from: outputImage.extent)
        }
        return nil
    }
}

// MARK: - Card
struct CompetitionCard: View {
    let c: Competition
    let isFavorited: Bool
    var onFavorite: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 0) {
            // Category Stripe
            CategoryStripe(category: c.category?.first)
            
            VStack(alignment: .leading, spacing: 8) {
                // Header: Source Badge + Title
                HStack(alignment: .top, spacing: 8) {
                    SourceBadgeView(sourceName: c.sourceName)
                    Text(c.title)
                        .font(.system(size: 16, weight: .semibold))
                        .lineLimit(2)
                        .foregroundStyle(CompetitionTheme.textDark)
                        .fixedSize(horizontal: false, vertical: true) // Allow multiline
                }
                
                // Middle: Tags + Deadline
                HStack {
                    if let tags = c.tags, !tags.isEmpty {
                        HStack(spacing: 4) {
                            ForEach(tags.prefix(3), id: \.self) { tag in
                                Text(tag)
                                    .font(.system(size: 10))
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.gray.opacity(0.1))
                                    .foregroundStyle(.secondary)
                                    .cornerRadius(4)
                            }
                            if tags.count > 3 {
                                Text("+\(tags.count - 3)")
                                    .font(.system(size: 10))
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    Spacer()
                    DeadlinePillView(deadlineDate: c.deadlineDate)
                }
                
                // Footer: Prize + Action
                HStack(alignment: .bottom) {
                    PrizeView(amount: c.bonusAmount, text: c.bonusText)
                    Spacer()
                    Button(action: { onFavorite?() }) {
                        Image(systemName: isFavorited ? "heart.fill" : "heart")
                            .foregroundStyle(isFavorited ? .red : .gray)
                            .padding(8)
                    }
                }
            }
            .padding(12)
        }
        .background(CompetitionTheme.backgroundLight)
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
        .opacity(isExpired ? 0.6 : 1.0)
    }
    
    var isExpired: Bool {
        guard let d = c.deadlineDate else { return false }
        return d < Date()
    }
}

// MARK: - Root Tabs
struct RootTabs: View {
    // Environment objects are injected from App root, no need to create them here
    // But we keep them here for preview compatibility if needed, or better, remove @StateObject if injected from App
    // To follow best practice and fix crash, we should rely on EnvironmentObject or keep StateObject here if it's the owner.
    // Since we moved StateObject to App, we should change these to EnvironmentObject or just remove them if passed down.
    // However, RootTabs is the root view used in App.swift.
    // Let's use @EnvironmentObject here to consume what App provides.
    
    // Actually, if we use @StateObject in App, we don't need them here as StateObject.
    // But RootTabs is the TabView.
    // Let's remove @StateObject from here and rely on Environment injection from App.
    
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("赛事", systemImage: "bolt.fill") }
            
            FavoritesView()
                .tabItem { Label("收藏", systemImage: "heart.fill") }
            
            SettingsView()
                .tabItem { Label("设置", systemImage: "gearshape.fill") }
        }
        // .task { await feed.load() } // Move load to HomeView or App onAppear
    }
}

// ... (rest of UI.swift)

// MARK: - Previews
#Preview {
    RootTabs()
        .environmentObject(FeedStore())
        .environmentObject(FavoritesStore())
}

struct QuickFilterBar: View {
    @Binding var filter: FilterState
    
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ChipButton(title: "全部", isSelected: isDefaultFilter) {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        filter = FilterState()
                    }
                }
                
                ChipButton(title: "高奖金 ≥1万", isSelected: filter.bonusTier == .k10) {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        if filter.bonusTier == .k10 {
                            filter.bonusTier = .all
                        } else {
                            filter.bonusTier = .k10
                        }
                    }
                }
                
                ChipButton(title: "奖金 ≥5000", isSelected: filter.bonusTier == .k5) {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        if filter.bonusTier == .k5 {
                            filter.bonusTier = .all
                        } else {
                            filter.bonusTier = .k5
                        }
                    }
                }
                
                ChipButton(title: "即将截止 7天", isSelected: filter.onlyRecentDeadline) {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        filter.onlyRecentDeadline.toggle()
                    }
                }
                
                if !isDefaultFilter {
                    Button("清除条件") {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                            filter = FilterState()
                        }
                    }
                    .font(.system(size: 13))
                    .foregroundStyle(.blue)
                    .padding(.leading, 4)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .background(Color(.systemGroupedBackground))
    }
    
    private var isDefaultFilter: Bool {
        filter.bonusTier == .all && !filter.onlyRecentDeadline && filter.selectedCategories.isEmpty && filter.sortOption == .latest
    }
}

// MARK: - Home
struct HomeView: View {
    @EnvironmentObject var feed: FeedStore
    @EnvironmentObject var fav: FavoritesStore
    @State private var query = ""
    @State private var filter = FilterState()
    @State private var showFilter = false

    private var allCategories: [String] {
        let cats = feed.items.flatMap { $0.category ?? [] }
        return Array(Set(cats)).sorted()
    }

    private var filtered: [Competition] {
        var result = feed.items
        
        // 1. Search
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !q.isEmpty {
            result = result.filter {
                $0.title.lowercased().contains(q) ||
                ($0.sourceName ?? "").lowercased().contains(q) ||
                ($0.tags ?? []).joined(separator: " ").lowercased().contains(q)
            }
        }
        
        // 2. Filter - Bonus
        if filter.bonusTier != .all {
            result = result.filter { ($0.bonusAmount ?? 0) >= filter.bonusTier.minAmount }
        }
        
        // 3. Filter - Deadline
        if filter.onlyRecentDeadline {
            let now = Calendar.current.startOfDay(for: Date())
            if let sevenDaysLater = Calendar.current.date(byAdding: .day, value: 7, to: now) {
                result = result.filter {
                    guard let d = $0.deadlineDate else { return false }
                    return d >= now && d <= sevenDaysLater
                }
            }
        }
        
        // 4. Filter - Categories
        if !filter.selectedCategories.isEmpty {
            result = result.filter {
                let itemCats = Set($0.category ?? [])
                return !itemCats.isDisjoint(with: filter.selectedCategories)
            }
        }
        
        // 5. Sort
        switch filter.sortOption {
        case .latest:
            // Assuming feed is implicitly latest-first. If not, we might need an ID or index.
            break
        case .highBonus:
            result.sort { ($0.bonusAmount ?? 0) > ($1.bonusAmount ?? 0) }
        case .soonestDeadline:
            result.sort {
                guard let d1 = $0.deadlineDate else { return false }
                guard let d2 = $1.deadlineDate else { return true }
                return d1 < d2
            }
        }
        
        return result
    }

    private var uniqueFiltered: [Competition] {
        var seen = Set<String>()
        var out: [Competition] = []
        for item in filtered {
            if !seen.contains(item.id) {
                seen.insert(item.id)
                out.append(item)
            }
        }
        return out
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                QuickFilterBar(filter: $filter)
                    .background(Color(.systemGroupedBackground))
                    .zIndex(1) // Ensure bar stays on top visually

                if feed.isLoading && feed.items.isEmpty {
                    ScrollView {
                        VStack(spacing: 12) {
                            ForEach(0..<6) { _ in SkeletonCard() }
                        }
                        .padding(16)
                    }
                } else if let err = feed.errorMessage, feed.items.isEmpty {
                    VStack(spacing: 12) {
                        Text(err).foregroundStyle(.secondary)
                        Button("重试") { Task { await feed.refresh() } }
                    }
                    .frame(maxHeight: .infinity)
                } else if filtered.isEmpty {
                    Text("暂无数据")
                        .foregroundStyle(.secondary)
                        .frame(maxHeight: .infinity)
                } else {
                    List {
                        ForEach(uniqueFiltered, id: \.id) { c in
                            ZStack {
                                NavigationLink {
                                    DetailView(c: c)
                                } label: {
                                    EmptyView()
                                }
                                .opacity(0) // Hide default arrow
                                
                                CompetitionCard(c: c, isFavorited: fav.contains(c.id)) {
                                    fav.toggle(c.id)
                                }
                            }
                            .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                            .listRowSeparator(.hidden)
                            .listRowBackground(Color.clear)
                            .contextMenu {
                                Button(fav.contains(c.id) ? "取消收藏" : "收藏") {
                                    fav.toggle(c.id)
                                }
                            }
                        }
                    }
                    .listStyle(.plain)
                    .background(Color(.systemGroupedBackground))
                    .refreshable { await feed.refresh() }
                }
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("赛事雷达")
            .searchable(text: $query, prompt: "搜索标题/标签/来源")
            .task {
                // Load data when Home appears if not loaded
                if feed.items.isEmpty {
                    await feed.load()
                }
            }
            .toolbar {
                Button {
                    showFilter = true
                } label: {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                        .symbolVariant(filter.bonusTier != .all || filter.onlyRecentDeadline || !filter.selectedCategories.isEmpty ? .fill : .none)
                }
            }
            .sheet(isPresented: $showFilter) {
                FilterSheetView(filter: $filter, allCategories: allCategories)
                    .presentationDetents([.medium, .large])
            }
            .overlay(alignment: .top) {
                if let err = feed.errorMessage, !feed.items.isEmpty {
                    Text("网络不可用，已显示缓存数据")
                        .font(.caption)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.black.opacity(0.7))
                        .clipShape(Capsule())
                        .padding(.top, 8)
                        .transition(.move(edge: .top).combined(with: .opacity))
                        .onAppear {
                            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                                // Logic to hide toast could be added here if we manage error state separately
                            }
                        }
                }
            }
        }
    }
}

struct ChipButton: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 13, weight: .medium))
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isSelected ? Color.blue : Color.white)
                .foregroundStyle(isSelected ? .white : .primary)
                .clipShape(Capsule())
                .shadow(color: .black.opacity(0.05), radius: 2, x: 0, y: 1)
        }
    }
}

struct ShareWrapper: Identifiable {
    let id = UUID()
    let items: [Any]
}

// MARK: - Detail
struct DetailView: View {
    let c: Competition
    @EnvironmentObject var fav: FavoritesStore
    @State private var shareWrapper: ShareWrapper?
    @State private var shareError = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Hero Card
                VStack(alignment: .leading, spacing: 16) {
                    HStack {
                        CategoryStripe(category: c.category?.first)
                            .frame(height: 24)
                        SourceBadgeView(sourceName: c.sourceName)
                        Spacer()
                        DeadlinePillView(deadlineDate: c.deadlineDate)
                    }
                    
                    Text(c.title)
                        .font(.title2.bold())
                        .foregroundStyle(CompetitionTheme.textDark)
                    
                    HStack {
                        PrizeView(amount: c.bonusAmount, text: c.bonusText)
                        Spacer()
                    }
                    
                    if let tags = c.tags, !tags.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack {
                                ForEach(tags, id: \.self) { tag in
                                    Text(tag)
                                        .font(.caption)
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(Color.gray.opacity(0.1))
                                        .cornerRadius(4)
                                }
                            }
                        }
                    }
                }
                .padding(CompetitionTheme.paddingLarge)
                .background(CompetitionTheme.backgroundLight)
                .cornerRadius(CompetitionTheme.cardRadius)
                .shadow(color: .black.opacity(0.05), radius: 8, x: 0, y: 4)
                
                // Content
                VStack(alignment: .leading, spacing: 12) {
                    Text("详情")
                        .font(.headline)
                    
                    Text(c.summary ?? "暂无简介")
                        .font(.body)
                        .foregroundStyle(CompetitionTheme.textLight)
                        .lineSpacing(4)
                }
                .padding()
                
                // Compliance / Source Footer
                VStack(alignment: .leading, spacing: 12) {
                    Divider()
                    
                    HStack {
                        Text("信息来源")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                        if let url = URL(string: c.sourceUrl) {
                            Link(c.sourceName ?? "查看来源", destination: url)
                                .font(.subheadline)
                        }
                    }
                    
                    Text("免责声明：本页面信息仅供参考，报名与具体规则请以官方网页为准。RaceRadar 仅提供信息聚合服务。")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal)
                .padding(.bottom, 8)
                
                Button(action: {
                    if let url = URL(string: c.sourceUrl) {
                        UIApplication.shared.open(url)
                    }
                }) {
                    Text("访问官网")
                        .font(.headline)
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(CompetitionTheme.primaryBlue)
                        .cornerRadius(12)
                }
                .padding()
            }
            .padding()
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("赛事详情")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                HStack {
                    Button(action: {
                        fav.toggle(c.id)
                    }) {
                        Image(systemName: fav.contains(c.id) ? "heart.fill" : "heart")
                            .foregroundStyle(fav.contains(c.id) ? .red : .primary)
                    }
                    
                    Button {
                        Task { @MainActor in
                            if let image = PosterRenderer.renderPoster(for: c) {
                                shareWrapper = ShareWrapper(items: [image])
                            } else {
                                shareError = true
                            }
                        }
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                }
            }
        }
        .sheet(item: $shareWrapper) { wrapper in
            ShareSheet(items: wrapper.items)
        }
        .alert("海报生成失败", isPresented: $shareError) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("请检查 sourceUrl 是否为空，以及 PosterView 是否有白底/固定尺寸。")
        }
    }
}

struct ShareSheet: UIViewControllerRepresentable {
    var items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}


// MARK: - Favorites
struct FavoritesView: View {
    @EnvironmentObject var feed: FeedStore
    @EnvironmentObject var fav: FavoritesStore

    private var items: [Competition] { feed.items.filter { fav.contains($0.id) } }

    var body: some View {
        NavigationStack {
            ZStack {
                Color(.systemGroupedBackground).ignoresSafeArea()
                if items.isEmpty {
                    Text("还没有收藏").foregroundStyle(.secondary)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(items) { c in
                                NavigationLink { DetailView(c: c) } label: {
                                    CompetitionCard(c: c, isFavorited: true) {
                                        fav.toggle(c.id)
                                    }
                                }
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 12)
                    }
                }
            }
            .navigationTitle("收藏")
        }
    }
}

// MARK: - Filter Sheet
struct FilterSheetView: View {
    @Binding var filter: FilterState
    let allCategories: [String]
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("奖金要求") {
                    Picker("最低奖金", selection: $filter.bonusTier) {
                        ForEach(BonusTier.allCases) { tier in
                            Text(tier.rawValue).tag(tier)
                        }
                    }
                }
                
                Section("时间要求") {
                    Toggle("即将截止 (7天内)", isOn: $filter.onlyRecentDeadline)
                    Toggle("显示已截止赛事 (历史)", isOn: $filter.showHistory)
                }
                
                Section("排序方式") {
                    Picker("排序", selection: $filter.sortOption) {
                        ForEach(SortOption.allCases) { option in
                            Text(option.rawValue).tag(option)
                        }
                    }
                }
                
                Section("类别筛选") {
                    if allCategories.isEmpty {
                        Text("无可用类别").foregroundStyle(.secondary)
                    } else {
                        ForEach(allCategories, id: \.self) { cat in
                            Button {
                                if filter.selectedCategories.contains(cat) {
                                    filter.selectedCategories.remove(cat)
                                } else {
                                    filter.selectedCategories.insert(cat)
                                }
                            } label: {
                                HStack {
                                    Text(cat)
                                    Spacer()
                                    if filter.selectedCategories.contains(cat) {
                                        Image(systemName: "checkmark").foregroundStyle(.blue)
                                    }
                                }
                            }
                            .foregroundStyle(.primary)
                        }
                    }
                }
            }
            .navigationTitle("筛选")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") { dismiss() }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button("重置") {
                        filter = FilterState()
                    }
                }
            }
        }
    }
}

// MARK: - Settings
struct SettingsView: View {
    @EnvironmentObject var feed: FeedStore
    @State private var showCopiedToast = false
    
    var body: some View {
        NavigationStack {
            List {
                Section("关于") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("赛事雷达 RaceRadar")
                            .font(.headline)
                        Text("本应用致力于为大学生聚合公开、优质的学科竞赛信息。所有信息均来自公开网络或官方渠道，仅供检索参考。")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                    
                    Link("隐私政策", destination: Constants.privacyURL)
                }
                
                Section("支持与反馈") {
                    if let url = URL(string: "mailto:\(Constants.supportEmail)") {
                        Link("联系我们", destination: url)
                    }
                    
                    Button("复制调试信息") {
                        let info = """
                        App Version: 1.0.0
                        Device: \(UIDevice.current.systemName) \(UIDevice.current.systemVersion)
                        Feed Updated: \(feed.updatedAt)
                        Items: \(feed.items.count)
                        """
                        UIPasteboard.general.string = info
                        showCopiedToast = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            showCopiedToast = false
                        }
                    }
                }
                
                Section("数据状态") {
                    LabeledContent("数据源更新", value: feed.updatedAt)
                    LabeledContent("当前条目数", value: "\(feed.items.count)")
                    
                    Button("清除缓存并刷新") {
                        Task { await feed.reloadIgnoringCache() }
                    }
                    .foregroundStyle(.red)
                    
                    Button("强制刷新 (Force Refresh)") {
                        Task { await feed.refresh() } // In real implementation pass true for force
                    }
                    .foregroundStyle(.orange)
                }
            }
            .navigationTitle("设置")
            .overlay(alignment: .bottom) {
                if showCopiedToast {
                    Text("已复制到剪贴板")
                        .font(.caption)
                        .padding()
                        .background(.thinMaterial)
                        .clipShape(Capsule())
                        .padding(.bottom, 20)
                }
            }
        }
    }
}
