import SwiftUI

@main
struct ExpenseVibeApp: App {
    @State private var session = Session()

    var body: some Scene {
        WindowGroup {
            Group {
                if session.isLoggedIn {
                    MainTabView()
                } else {
                    LoginView()
                }
            }
            // Delad fil (CFBundleDocumentTypes) eller länken "Öppna i appen" på webbsidan Mobilappen.
            .onOpenURL { url in
                if url.isFileURL {
                    session.sharedFile = url
                } else {
                    Task { _ = await session.handle(url: url) }
                }
            }
        }
        .environment(session)
    }
}

struct MainTabView: View {
    @Environment(Session.self) private var session
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TabView {
            ExpensesView()
                .tabItem { Label("Utlägg", systemImage: "receipt") }
            MileageView()
                .tabItem { Label("Körjournal", systemImage: "car") }
            AbsenceView()
                .tabItem { Label("Frånvaro", systemImage: "calendar") }
            if session.user?.isApprover == true {
                ApprovalsView()
                    .tabItem { Label("Attestering", systemImage: "checkmark.seal") }
            }
            AccountView()
                .tabItem { Label("Konto", systemImage: "person.circle") }
        }
        .onChange(of: scenePhase, initial: true) { _, phase in
            if phase == .active { Task { await session.refreshUser() } }
        }
        // Ligger här och inte i ExpensesView: en flik som inte visas kan inte visa ett ark.
        .sheet(isPresented: Binding(get: { session.sharedFile != nil }, set: { if !$0 { session.sharedFile = nil } })) {
            NewExpenseView(sharedFile: session.sharedFile)
        }
    }
}

struct LoginView: View {
    @Environment(Session.self) private var session
    @State private var server = ""
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?
    @State private var showScanner = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("https://expensevibe.example.se", text: $server)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Section("Inloggning") {
                    TextField("E-postadress", text: $email)
                        .keyboardType(.emailAddress)
                        .textContentType(.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Lösenord", text: $password)
                        .textContentType(.password)
                }
                Button {
                    Task { await login() }
                } label: {
                    HStack {
                        Spacer()
                        if busy { ProgressView() } else { Text("Logga in") }
                        Spacer()
                    }
                }
                .disabled(busy || server.isEmpty || email.isEmpty || password.isEmpty)
                Section {
                    Button {
                        showScanner = true
                    } label: {
                        Label("Skanna QR-kod", systemImage: "qrcode.viewfinder")
                    }
                    .disabled(busy)
                } footer: {
                    Text("QR-koden finns under Mobilappen i menyn i webbappen.")
                }
            }
            .navigationTitle("ExpenseVibe")
            .onAppear { server = session.baseURL }
            .sheet(isPresented: $showScanner) {
                QRScannerSheet { url in
                    showScanner = false
                    Task {
                        busy = true
                        error = await session.handle(url: url)
                        busy = false
                    }
                }
            }
            .errorAlert($error)
        }
    }

    private func login() async {
        busy = true
        defer { busy = false }
        do {
            try await session.login(server: server, email: email, password: password)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct AccountView: View {
    @Environment(Session.self) private var session

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    LabeledContent("Namn", value: session.user?.name ?? "")
                    LabeledContent("E-post", value: session.user?.email ?? "")
                    LabeledContent("Roll", value: session.user?.isApprover == true ? "Attestant" : "Anställd")
                    LabeledContent("Server", value: session.baseURL)
                }
                Section {
                    Text("Export till Visma, användare och övriga inställningar hanteras i webbappen.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Button("Logga ut", role: .destructive) {
                    Task { await session.logout() }
                }
            }
            .navigationTitle("Konto")
        }
    }
}

// MARK: - Delade småbitar

struct StatusBadge: View {
    let status: String
    let text: String

    private var color: Color {
        switch status {
        case "approved": .green
        case "rejected": .red
        case "exported": .blue
        default: .orange
        }
    }

    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }
}

extension View {
    func errorAlert(_ error: Binding<String?>) -> some View {
        alert(
            "Något gick fel",
            isPresented: Binding(get: { error.wrappedValue != nil }, set: { if !$0 { error.wrappedValue = nil } })
        ) {
            Button("OK") {}
        } message: {
            Text(error.wrappedValue ?? "")
        }
    }
}

/// Attestera/avvisa-knappar för attestanten; stängs (poppar) när beslutet är sparat.
struct DecisionSection: View {
    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    let kind: String
    let id: Int
    @State private var askReason = false
    @State private var reason = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        Section {
            Button {
                Task { await decide("approve", [:]) }
            } label: {
                Label("Attestera", systemImage: "checkmark.circle.fill").frame(maxWidth: .infinity)
            }
            .tint(.green)
            Button(role: .destructive) {
                askReason = true
            } label: {
                Label("Avvisa", systemImage: "xmark.circle").frame(maxWidth: .infinity)
            }
        }
        .disabled(busy)
        .alert("Avvisa", isPresented: $askReason) {
            TextField("Anledning", text: $reason)
            Button("Avvisa", role: .destructive) { Task { await decide("reject", ["reason": reason]) } }
            Button("Avbryt", role: .cancel) {}
        } message: {
            Text("Anledningen visas för den anställde.")
        }
        .errorAlert($error)
    }

    private func decide(_ action: String, _ body: [String: Any]) async {
        struct Ok: Decodable { let ok: Bool }
        busy = true
        defer { busy = false }
        do {
            let _: Ok = try await session.post("approvals/\(kind)/\(id)/\(action)/", json: body)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
