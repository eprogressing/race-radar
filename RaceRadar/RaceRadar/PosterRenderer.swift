import SwiftUI
import UIKit
import CoreImage
import CoreImage.CIFilterBuiltins

enum PosterRenderer {
    private static let ciContext = CIContext()
    private static let qrFilter = CIFilter.qrCodeGenerator()

    static func makeQRCode(from text: String, size: CGFloat = 260) -> UIImage? {
        let data = Data(text.utf8)
        qrFilter.setValue(data, forKey: "inputMessage")
        qrFilter.setValue("M", forKey: "inputCorrectionLevel")

        guard let output = qrFilter.outputImage else { return nil }
        let extent = output.extent.integral
        let scale = min(size / extent.width, size / extent.height)
        let transformed = output.transformed(by: CGAffineTransform(scaleX: scale, y: scale))

        guard let cg = ciContext.createCGImage(transformed, from: transformed.extent) else { return nil }
        return UIImage(cgImage: cg)
    }

    @MainActor
    static func renderPoster(for competition: Competition) -> UIImage? {
        let urlString = competition.sourceUrl.trimmingCharacters(in: .whitespacesAndNewlines)
        let qr = makeQRCode(from: urlString)

        let posterView = PosterView(competition: competition, qrImage: qr)
            .frame(width: 1080, height: 1920)
            .background(Color.white)
            .environment(\.colorScheme, .light)

        if #available(iOS 16.0, *) {
            let renderer = ImageRenderer(content: posterView)
            renderer.scale = 3
            renderer.isOpaque = true
            return renderer.uiImage
        }

        let host = UIHostingController(rootView: posterView)
        host.view.bounds = CGRect(x: 0, y: 0, width: 1080, height: 1920)
        host.view.backgroundColor = .white

        let format = UIGraphicsImageRendererFormat()
        format.scale = 3
        format.opaque = true

        let r = UIGraphicsImageRenderer(size: host.view.bounds.size, format: format)
        return r.image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }
}
