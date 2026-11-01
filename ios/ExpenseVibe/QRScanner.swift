import SwiftUI
import VisionKit

/// Läser QR-koden från webbsidan Mobilappen (accounts.views.mobile_app), som i SaldoVibe.
struct QRScannerSheet: View {
    let onFound: (URL) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if DataScannerViewController.isSupported && DataScannerViewController.isAvailable {
                    QRScannerView(onFound: onFound).ignoresSafeArea()
                } else {
                    ContentUnavailableView(
                        "Kameran kan inte användas",
                        systemImage: "camera",
                        description: Text("Skanning kräver en iPhone med kamera och att appen får använda den (Inställningar → ExpenseVibe → Kamera).")
                    )
                }
            }
            .navigationTitle("Skanna QR-kod")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Avbryt") { dismiss() }
                }
            }
        }
    }
}

private struct QRScannerView: UIViewControllerRepresentable {
    let onFound: (URL) -> Void

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let scanner = DataScannerViewController(
            recognizedDataTypes: [.barcode(symbologies: [.qr])],
            qualityLevel: .balanced,
            isHighlightingEnabled: true
        )
        scanner.delegate = context.coordinator
        return scanner
    }

    func updateUIViewController(_ scanner: DataScannerViewController, context: Context) {
        if !scanner.isScanning {
            try? scanner.startScanning()
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(onFound: onFound) }

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let onFound: (URL) -> Void
        private var done = false

        init(onFound: @escaping (URL) -> Void) { self.onFound = onFound }

        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            guard !done else { return }
            for item in addedItems {
                if case .barcode(let barcode) = item, let text = barcode.payloadStringValue,
                   let url = URL(string: text), url.scheme == "expensevibe" {
                    done = true
                    dataScanner.stopScanning()
                    onFound(url)
                    return
                }
            }
        }
    }
}
