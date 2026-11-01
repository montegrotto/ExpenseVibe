import PhotosUI
import SwiftUI
import WebKit

struct ExpensesView: View {
    @Environment(Session.self) private var session
    @State private var expenses: [Expense] = []
    @State private var showNew = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List(expenses) { expense in
                NavigationLink(value: expense) { ExpenseRow(expense: expense) }
            }
            .overlay {
                if expenses.isEmpty {
                    ContentUnavailableView("Inga utlägg", systemImage: "receipt", description: Text("Tryck på plus för att skicka in ett kvitto."))
                }
            }
            .navigationTitle("Mina utlägg")
            .navigationDestination(for: Expense.self) { ExpenseDetailView(expense: $0) }
            .toolbar {
                Button { showNew = true } label: { Image(systemName: "plus") }
            }
            .sheet(isPresented: $showNew, onDismiss: { Task { await load() } }) { NewExpenseView() }
            .task { await load() }
            .onChange(of: session.sharedFile) { _, file in if file == nil { Task { await load() } } }
            .refreshable { await load() }
            .errorAlert($error)
        }
    }

    private func load() async {
        do {
            let response: Results<Expense> = try await session.get("expenses/")
            expenses = response.results
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct ExpenseRow: View {
    let expense: Expense
    var showEmployee = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(expense.description).font(.headline)
                Spacer()
                Text("\(expense.amount) \(expense.currency)").font(.headline.monospacedDigit())
            }
            HStack {
                Text(showEmployee ? expense.employee : expense.category)
                Text("·")
                Text(expense.expenseDate)
                Spacer()
                StatusBadge(status: expense.status, text: expense.statusDisplay)
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
            if !expense.decisionComment.isEmpty {
                Text(expense.decisionComment).font(.footnote).foregroundStyle(.red)
            }
        }
        .padding(.vertical, 2)
    }
}

struct ExpenseDetailView: View {
    let expense: Expense
    var decide = false

    var body: some View {
        List {
            Section {
                LabeledContent("Anställd", value: expense.employee)
                LabeledContent("Kategori", value: expense.category)
                LabeledContent("Datum", value: expense.expenseDate)
                LabeledContent("Belopp", value: "\(expense.amount) \(expense.currency)")
                if let vat = expense.vatAmount {
                    LabeledContent("Varav moms", value: "\(vat) \(expense.currency)")
                }
                LabeledContent("Status") { StatusBadge(status: expense.status, text: expense.statusDisplay) }
                if !expense.decisionComment.isEmpty {
                    LabeledContent("Kommentar", value: expense.decisionComment)
                }
            }
            Section("Kvitto") {
                ReceiptView(attachmentId: expense.attachmentId, interactive: false)
                    .frame(height: 320)
                    .listRowInsets(EdgeInsets())
                NavigationLink("Öppna kvittot") {
                    ReceiptView(attachmentId: expense.attachmentId, interactive: true)
                        .ignoresSafeArea(edges: .bottom)
                        .navigationTitle("Kvitto")
                        .navigationBarTitleDisplayMode(.inline)
                }
            }
            if decide {
                DecisionSection(kind: "utlagg", id: expense.id)
            }
        }
        .navigationTitle(expense.description)
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// Hämtar kvittofilen med token (AsyncImage kan inte sätta Authorization)
/// och visar den i en WKWebView, som renderar både bilder och PDF.
struct ReceiptView: View {
    @Environment(Session.self) private var session
    let attachmentId: Int
    let interactive: Bool
    @State private var file: (data: Data, mimeType: String)?
    @State private var failed = false

    var body: some View {
        Group {
            if let file {
                WebDocument(data: file.data, mimeType: file.mimeType, interactive: interactive)
            } else if failed {
                Text("Kvittot kunde inte hämtas.").foregroundStyle(.secondary).frame(maxWidth: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity)
            }
        }
        .task {
            do {
                let (data, mimeType) = try await session.data("GET", "attachments/\(attachmentId)/file/")
                file = (data, mimeType ?? "image/jpeg")
            } catch {
                failed = true
            }
        }
    }
}

struct WebDocument: UIViewRepresentable {
    let data: Data
    let mimeType: String
    let interactive: Bool

    func makeUIView(context: Context) -> WKWebView {
        let view = WKWebView()
        view.isOpaque = false
        view.scrollView.isScrollEnabled = interactive
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        if mimeType.hasPrefix("image/") {
            let html = "<meta name=viewport content='width=device-width,initial-scale=1'>"
                + "<body style='margin:0'><img src='data:\(mimeType);base64,\(data.base64EncodedString())' style='width:100%'></body>"
            view.loadHTMLString(html, baseURL: nil)
        } else {
            view.load(data, mimeType: mimeType, characterEncodingName: "utf-8", baseURL: URL(string: "about:blank")!)
        }
    }
}

struct NewExpenseView: View {
    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    var sharedFile: URL?
    @State private var categories: [Category] = []
    @State private var photoItem: PhotosPickerItem?
    @State private var image: UIImage?
    @State private var pdf: Data?
    @State private var attachmentId: Int?
    @State private var uploading = false
    @State private var showCamera = false
    @State private var category: Category?
    @State private var description = ""
    @State private var date = Date()
    @State private var amount = ""
    @State private var vat = ""
    @State private var currency = "SEK"
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Kvitto") {
                    if let image {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFit()
                            .frame(maxWidth: .infinity, maxHeight: 220)
                    }
                    if let pdf {
                        WebDocument(data: pdf, mimeType: "application/pdf", interactive: false)
                            .frame(height: 220)
                    }
                    HStack {
                        if UIImagePickerController.isSourceTypeAvailable(.camera) {
                            Button { showCamera = true } label: { Label("Fotografera", systemImage: "camera") }
                            Spacer()
                        }
                        PhotosPicker(selection: $photoItem, matching: .images) { Label("Välj bild", systemImage: "photo") }
                    }
                    .buttonStyle(.borderless)
                    if uploading {
                        HStack {
                            ProgressView()
                            Text("Laddar upp och läser kvittot…").foregroundStyle(.secondary)
                        }
                    }
                }
                Section("Uppgifter") {
                    Picker("Kategori", selection: $category) {
                        Text("Välj…").tag(Category?.none)
                        ForEach(categories) { Text($0.name).tag(Optional($0)) }
                    }
                    TextField("Beskrivning", text: $description)
                    DatePicker("Datum", selection: $date, displayedComponents: .date)
                    TextField("Belopp", text: $amount).keyboardType(.decimalPad)
                    TextField("Varav moms (valfritt)", text: $vat).keyboardType(.decimalPad)
                    TextField("Valuta", text: $currency).textInputAutocapitalization(.characters)
                }
            }
            .navigationTitle("Nytt utlägg")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Avbryt") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Skicka in") { Task { await save() } }
                        .disabled(attachmentId == nil || uploading || saving)
                }
            }
            .task {
                do {
                    let response: Results<Category> = try await session.get("categories/")
                    categories = response.results
                } catch {
                    self.error = error.localizedDescription
                }
                if let sharedFile { await upload(file: sharedFile) }
            }
            .onChange(of: photoItem) { _, item in
                guard let item else { return }
                Task {
                    if let data = try? await item.loadTransferable(type: Data.self), let picked = UIImage(data: data) {
                        await upload(picked)
                    }
                }
            }
            .fullScreenCover(isPresented: $showCamera) {
                CameraPicker { picked in Task { await upload(picked) } }.ignoresSafeArea()
            }
            .errorAlert($error)
        }
    }

    private func upload(_ picked: UIImage) async {
        // Krymp till max 2000 px: HEIC/12 MP-foton blir JPEG som servern tar
        // emot, och ReInvGrabber hinner läsa dem inom timeouten.
        let scale = min(1, 2000 / max(picked.size.width, picked.size.height))
        let size = CGSize(width: picked.size.width * scale, height: picked.size.height * scale)
        let resized = picked.preparingThumbnail(of: size) ?? picked
        image = resized
        pdf = nil
        guard let jpeg = resized.jpegData(compressionQuality: 0.85) else { return }
        await upload(jpeg, fileName: "kvitto.jpg", mimeType: "image/jpeg")
    }

    /// Delad fil från t.ex. Mail. iOS lägger en kopia i Documents/Inbox, som tas bort när den är läst.
    private func upload(file url: URL) async {
        defer { try? FileManager.default.removeItem(at: url) }
        guard let data = try? Data(contentsOf: url) else {
            error = "Filen kunde inte läsas."
            return
        }
        if url.pathExtension.lowercased() == "pdf" {
            image = nil
            pdf = data
            await upload(data, fileName: url.lastPathComponent, mimeType: "application/pdf")
        } else if let picked = UIImage(data: data) {
            await upload(picked)
        } else {
            error = "Bara PDF och bilder kan bli kvitton."
        }
    }

    private func upload(_ file: Data, fileName: String, mimeType: String) async {
        uploading = true
        defer { uploading = false }
        do {
            let result = try await session.upload(file, fileName: fileName, mimeType: mimeType)
            attachmentId = result.id
            if let suggested = result.suggested.amount, amount.isEmpty { amount = suggested }
            if let suggested = result.suggested.vatAmount, vat.isEmpty { vat = suggested }
            if let suggested = result.suggested.currency { currency = suggested }
            if let suggested = result.suggested.expenseDate, let parsed = Day.parse(suggested) { date = parsed }
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func save() async {
        guard let attachmentId else { return }
        saving = true
        defer { saving = false }
        do {
            let _: Expense = try await session.post("expenses/", json: [
                "attachment_id": attachmentId,
                "category": category.map { $0.id } ?? NSNull(),
                "description": description,
                "expense_date": Day.string(date),
                "amount": amount.decimal,
                "vat_amount": vat.decimal,
                "currency": currency,
            ])
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct CameraPicker: UIViewControllerRepresentable {
    let onImage: (UIImage) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker

        init(_ parent: CameraPicker) { self.parent = parent }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage {
                parent.onImage(image)
            }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}
