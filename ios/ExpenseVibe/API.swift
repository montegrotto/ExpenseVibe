import Foundation
import Observation
import Security
import UIKit

// Speglar JSON-svaren i api/views.py (snake_case -> camelCase via JSONDecoder).
// Belopp och datum lämnas som strängar: servern formaterar Decimal/date
// redan rätt, och appen räknar aldrig på dem.

struct User: Codable {
    let id: Int
    let name: String
    let email: String
    let isApprover: Bool
}

struct Category: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
}

struct Expense: Decodable, Identifiable, Hashable {
    let id: Int
    let employee: String
    let description: String
    let category: String
    let expenseDate: String
    let amount: String
    let vatAmount: String?
    let currency: String
    let status: String
    let statusDisplay: String
    let decisionComment: String
    let attachmentId: Int
}

struct MileageReport: Decodable, Identifiable, Hashable {
    let id: Int
    let employee: String
    let date: String
    let startLocation: String
    let endLocation: String
    let purpose: String
    let distanceKm: String
    let rateSnapshot: String
    let compensationAmount: String
    let status: String
    let statusDisplay: String
    let decisionComment: String
}

struct AbsenceType: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let granularity: String

    var isWholeDay: Bool { granularity == "whole_day" }
}

struct AbsenceEntry: Decodable, Identifiable, Hashable {
    let id: Int
    let date: String
    let absenceType: String
    let wholeDay: Bool
    let hours: String?
}

struct TimeReport: Decodable, Identifiable, Hashable {
    let id: Int
    let employee: String
    let period: String
    let status: String
    let statusDisplay: String
    let decisionComment: String
    let entries: [AbsenceEntry]
}

struct AbsenceMonth: Decodable {
    let month: String
    let periodOpen: Bool
    let canEdit: Bool
    let timeReport: TimeReport?
    let entries: [AbsenceEntry]
    let types: [AbsenceType]
}

struct Approvals: Decodable {
    var expenses: [Expense] = []
    var mileage: [MileageReport] = []
    var timeReports: [TimeReport] = []
}

struct Results<T: Decodable>: Decodable {
    let results: [T]
}

struct Upload: Decodable {
    struct Suggested: Decodable {
        let expenseDate: String?
        let amount: String?
        let vatAmount: String?
        let currency: String?
    }

    let id: Int
    let suggested: Suggested
}

struct APIError: LocalizedError {
    let message: String
    var status = 0
    var errorDescription: String? { message }
}

@Observable @MainActor
final class Session {
    private(set) var baseURL: String
    private(set) var token: String?
    private(set) var user: User?
    /// PDF/bild delad till appen (t.ex. från Mail) som ska bli ett nytt utlägg.
    var sharedFile: URL?

    init() {
        baseURL = UserDefaults.standard.string(forKey: "baseURL") ?? ""
        token = Keychain.read()
        if let data = UserDefaults.standard.data(forKey: "user") {
            user = try? JSONDecoder().decode(User.self, from: data)
        }
    }

    var isLoggedIn: Bool { token != nil }

    func login(server: String, email: String, password: String) async throws {
        baseURL = Self.normalize(server)
        struct LoginResponse: Decodable {
            let token: String
            let user: User
        }
        let response: LoginResponse = try await send("POST", "login/", json: ["email": email, "password": password, "device_name": UIDevice.current.name])
        signIn(token: response.token, user: response.user)
    }

    /// QR-koden på webbsidan Mobilappen: expensevibe://login?server=…&token=… -
    /// token finns redan på servern. Returnerar ett felmeddelande, nil om det gick.
    func handle(url: URL) async -> String? {
        guard url.scheme == "expensevibe", url.host() == "login",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems,
              let server = items.first(where: { $0.name == "server" })?.value,
              let token = items.first(where: { $0.name == "token" })?.value, !token.isEmpty
        else { return "QR-koden är ingen ExpenseVibe-inloggning." }
        struct Me: Decodable { let user: User }
        var lastError: Error?
        for candidate in Self.serverCandidates(for: Self.normalize(server)) {
            baseURL = candidate
            do {
                let (data, _) = try await data("GET", "me/", bearer: token)
                signIn(token: token, user: try Self.decoder.decode(Me.self, from: data).user)
                return nil
            } catch {
                lastError = error
                if (error as? APIError)?.status == 401 { break }
            }
        }
        return lastError?.localizedDescription
    }

    /// En QR-kod gjord bakom en proxy som tappar X-Forwarded-Proto säger http fast sajten är
    /// https, och iOS vägrar ändå okrypterat mot domännamn. För ett domännamn provas https
    /// först och sedan det koden sa; IP-adresser, localhost, .local och okvalificerade namn
    /// (som iOS släpper fram över http) används som de är. Som i SaldoVibe.
    static func serverCandidates(for server: String) -> [String] {
        guard var components = URLComponents(string: server), components.scheme == "http",
              let host = components.host, !isLocalNetworkHost(host)
        else { return [server] }
        components.scheme = "https"
        if components.port == 80 { components.port = nil }
        return [components.string, server].compactMap { $0 }
    }

    static func isLocalNetworkHost(_ host: String) -> Bool {
        host == "localhost" || host.hasSuffix(".local") || !host.contains(".") || host.contains(":")
            || host.allSatisfy { $0.isNumber || $0 == "." }
    }

    private func signIn(token: String, user: User) {
        self.token = token
        self.user = user
        Keychain.save(token)
        UserDefaults.standard.set(baseURL, forKey: "baseURL")
        UserDefaults.standard.set(try? JSONEncoder().encode(user), forKey: "user")
    }

    private static func normalize(_ server: String) -> String {
        var url = server.trimmingCharacters(in: .whitespacesAndNewlines)
        while url.hasSuffix("/") { url.removeLast() }
        if !url.contains("://") { url = "https://" + url }
        return url
    }

    func logout() async {
        _ = try? await data("POST", "logout/")
        clear()
    }

    private func clear() {
        token = nil
        user = nil
        Keychain.save(nil)
        UserDefaults.standard.removeObject(forKey: "user")
    }

    func get<T: Decodable>(_ path: String) async throws -> T {
        try await send("GET", path)
    }

    func post<T: Decodable>(_ path: String, json: [String: Any]) async throws -> T {
        try await send("POST", path, json: json)
    }

    func upload(_ file: Data, fileName: String, mimeType: String) async throws -> Upload {
        let boundary = UUID().uuidString
        var body = Data()
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\nContent-Type: \(mimeType)\r\n\r\n".utf8))
        body.append(file)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        let (data, _) = try await data("POST", "attachments/", body: body, contentType: "multipart/form-data; boundary=\(boundary)")
        return try Self.decoder.decode(Upload.self, from: data)
    }

    private func send<T: Decodable>(_ method: String, _ path: String, json: [String: Any]? = nil) async throws -> T {
        var body: Data?
        var contentType: String?
        if let json {
            body = try JSONSerialization.data(withJSONObject: json)
            contentType = "application/json"
        }
        let (data, _) = try await data(method, path, body: body, contentType: contentType)
        return try Self.decoder.decode(T.self, from: data)
    }

    /// Rått anrop; returnerar svarskroppen och dess MIME-typ (för kvittofiler).
    /// `bearer` används innan token är sparad (QR-inloggningen).
    func data(_ method: String, _ path: String, body: Data? = nil, contentType: String? = nil, bearer: String? = nil) async throws -> (Data, String?) {
        guard let url = URL(string: baseURL + "/api/" + path) else {
            throw APIError(message: "Ogiltig serveradress.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        if let contentType {
            request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        }
        if let token = bearer ?? token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        if status == 401, token != nil {
            // Token återkallad (admin har satt nytt lösenord) - tillbaka till inloggningen.
            clear()
        }
        guard (200..<300).contains(status) else {
            throw APIError(message: Self.message(from: data, status: status), status: status)
        }
        return (data, response.mimeType)
    }

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    private static func message(from data: Data, status: Int) -> String {
        let fallback = "Servern svarade med fel \(status)."
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return fallback }
        if let error = object["error"] as? String { return error }
        if let errors = object["errors"] as? [String: [String]] {
            return errors.values.flatMap { $0 }.joined(separator: "\n")
        }
        return fallback
    }
}

enum Keychain {
    private static let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "se.damadev.expensevibe",
        kSecAttrAccount as String: "api-token",
    ]

    static func read() -> String? {
        var query = query
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    static func save(_ value: String?) {
        SecItemDelete(query as CFDictionary)
        guard let value else { return }
        var query = query
        query[kSecValueData as String] = Data(value.utf8)
        SecItemAdd(query as CFDictionary, nil)
    }
}

/// Datum som "yyyy-MM-dd" i lokal tidszon - samma format som Django-formulären tar emot.
enum Day {
    private static let formatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    static func string(_ date: Date) -> String { formatter.string(from: date) }
    static func parse(_ string: String) -> Date? { formatter.date(from: string) }
}

extension String {
    /// Svenskt decimalkomma -> punkt, så Django's DecimalField förstår det.
    var decimal: String { replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespaces) }
}
