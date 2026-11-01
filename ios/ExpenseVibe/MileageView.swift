import SwiftUI

struct MileageView: View {
    @Environment(Session.self) private var session
    @State private var reports: [MileageReport] = []
    @State private var showNew = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List(reports) { report in
                NavigationLink(value: report) { MileageRow(report: report) }
            }
            .overlay {
                if reports.isEmpty {
                    ContentUnavailableView("Inga resor", systemImage: "car", description: Text("Tryck på plus för att rapportera en resa."))
                }
            }
            .navigationTitle("Körjournal")
            .navigationDestination(for: MileageReport.self) { MileageDetailView(report: $0) }
            .toolbar {
                Button { showNew = true } label: { Image(systemName: "plus") }
            }
            .sheet(isPresented: $showNew, onDismiss: { Task { await load() } }) { NewMileageView() }
            .task { await load() }
            .refreshable { await load() }
            .errorAlert($error)
        }
    }

    private func load() async {
        do {
            let response: Results<MileageReport> = try await session.get("mileage/")
            reports = response.results
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct MileageRow: View {
    let report: MileageReport
    var showEmployee = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("\(report.startLocation) → \(report.endLocation)").font(.headline)
                Spacer()
                Text("\(report.compensationAmount) SEK").font(.headline.monospacedDigit())
            }
            HStack {
                Text(showEmployee ? report.employee : report.purpose)
                Text("·")
                Text(report.date)
                Text("·")
                Text("\(report.distanceKm) km")
                Spacer()
                StatusBadge(status: report.status, text: report.statusDisplay)
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
            if !report.decisionComment.isEmpty {
                Text(report.decisionComment).font(.footnote).foregroundStyle(.red)
            }
        }
        .padding(.vertical, 2)
    }
}

struct MileageDetailView: View {
    let report: MileageReport
    var decide = false

    var body: some View {
        List {
            Section {
                LabeledContent("Anställd", value: report.employee)
                LabeledContent("Datum", value: report.date)
                LabeledContent("Från", value: report.startLocation)
                LabeledContent("Till", value: report.endLocation)
                LabeledContent("Syfte", value: report.purpose)
                LabeledContent("Sträcka", value: "\(report.distanceKm) km")
                LabeledContent("Sats", value: "\(report.rateSnapshot) kr/km")
                LabeledContent("Ersättning", value: "\(report.compensationAmount) SEK")
                LabeledContent("Status") { StatusBadge(status: report.status, text: report.statusDisplay) }
                if !report.decisionComment.isEmpty {
                    LabeledContent("Kommentar", value: report.decisionComment)
                }
            }
            if decide {
                DecisionSection(kind: "kilometer", id: report.id)
            }
        }
        .navigationTitle("Kilometerrapport")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct NewMileageView: View {
    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var date = Date()
    @State private var from = ""
    @State private var to = ""
    @State private var purpose = ""
    @State private var distance = ""
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                DatePicker("Datum", selection: $date, displayedComponents: .date)
                TextField("Från", text: $from)
                TextField("Till", text: $to)
                TextField("Syfte", text: $purpose)
                TextField("Antal km", text: $distance).keyboardType(.decimalPad)
            }
            .navigationTitle("Ny resa")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Avbryt") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Skicka in") { Task { await save() } }.disabled(saving)
                }
            }
            .errorAlert($error)
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        do {
            let _: MileageReport = try await session.post("mileage/", json: [
                "date": Day.string(date),
                "start_location": from,
                "end_location": to,
                "purpose": purpose,
                "distance_km": distance.decimal,
            ])
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
