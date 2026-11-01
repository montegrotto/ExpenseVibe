import SwiftUI

struct ApprovalsView: View {
    @Environment(Session.self) private var session
    @State private var approvals = Approvals()
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                Section("Utlägg") {
                    ForEach(approvals.expenses) { expense in
                        NavigationLink(value: expense) { ExpenseRow(expense: expense, showEmployee: true) }
                    }
                    if approvals.expenses.isEmpty {
                        Text("Inga utlägg väntar.").foregroundStyle(.secondary)
                    }
                }
                Section("Kilometerrapporter") {
                    ForEach(approvals.mileage) { report in
                        NavigationLink(value: report) { MileageRow(report: report, showEmployee: true) }
                    }
                    if approvals.mileage.isEmpty {
                        Text("Inga kilometerrapporter väntar.").foregroundStyle(.secondary)
                    }
                }
                Section("Tidrapporter") {
                    ForEach(approvals.timeReports) { report in
                        NavigationLink(value: report) { TimeReportRow(report: report) }
                    }
                    if approvals.timeReports.isEmpty {
                        Text("Inga tidrapporter väntar.").foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Attestering")
            .navigationDestination(for: Expense.self) { ExpenseDetailView(expense: $0, decide: true) }
            .navigationDestination(for: MileageReport.self) { MileageDetailView(report: $0, decide: true) }
            .navigationDestination(for: TimeReport.self) { TimeReportDetailView(report: $0) }
            // onAppear (inte task) så att kön laddas om när detaljvyn poppar efter ett beslut.
            .onAppear { Task { await load() } }
            .refreshable { await load() }
            .errorAlert($error)
        }
    }

    private func load() async {
        do {
            approvals = try await session.get("approvals/")
        } catch {
            self.error = error.localizedDescription
        }
    }
}
