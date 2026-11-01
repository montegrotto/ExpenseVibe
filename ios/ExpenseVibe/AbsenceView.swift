import SwiftUI

/// Frånvarokalendern i webben som lista: en månad i taget, poster läggs till
/// och tas bort tills månaden markeras som färdig (då skickas tidrapporten).
struct AbsenceView: View {
    @Environment(Session.self) private var session
    @State private var month = Calendar.current.dateInterval(of: .month, for: Date())!.start
    @State private var data: AbsenceMonth?
    @State private var showNew = false
    @State private var busy = false
    @State private var confirmSubmit = false
    @State private var error: String?

    private static let titleFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "sv_SE")
        formatter.dateFormat = "LLLL yyyy"
        return formatter
    }()

    private var monthRange: ClosedRange<Date> {
        let interval = Calendar.current.dateInterval(of: .month, for: month)!
        return interval.start...interval.end.addingTimeInterval(-1)
    }

    private var canEdit: Bool { data?.canEdit == true }

    var body: some View {
        NavigationStack {
            List {
                if let report = data?.timeReport {
                    Section("Tidrapport") {
                        LabeledContent("Status") { StatusBadge(status: report.status, text: report.statusDisplay) }
                        if !report.decisionComment.isEmpty {
                            Text(report.decisionComment).foregroundStyle(.red)
                        }
                    }
                }
                Section {
                    ForEach(data?.entries ?? []) { entry in
                        AbsenceEntryRow(entry: entry).deleteDisabled(!canEdit)
                    }
                    .onDelete { offsets in Task { await delete(offsets) } }
                    if let data, data.entries.isEmpty {
                        Text(data.periodOpen ? "Ingen frånvaro registrerad." : "Perioden är inte öppnad ännu. Kontakta administratören.")
                            .foregroundStyle(.secondary)
                    }
                }
                if canEdit {
                    Section {
                        Button("Markera som färdig") { confirmSubmit = true }.disabled(busy)
                    } footer: {
                        Text("Skickar månadens tidrapport till attestering, även om du inte haft någon frånvaro.")
                    }
                }
            }
            .navigationTitle(Self.titleFormatter.string(from: month).capitalized)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarLeading) {
                    Button { shift(-1) } label: { Image(systemName: "chevron.left") }
                    Button { shift(1) } label: { Image(systemName: "chevron.right") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showNew = true } label: { Image(systemName: "plus") }.disabled(!canEdit)
                }
            }
            .sheet(isPresented: $showNew, onDismiss: { Task { await load() } }) {
                NewAbsenceView(range: monthRange, types: data?.types ?? [])
            }
            .confirmationDialog("Skicka tidrapporten till attestering?", isPresented: $confirmSubmit, titleVisibility: .visible) {
                Button("Markera som färdig") { Task { await submit() } }
                Button("Avbryt", role: .cancel) {}
            } message: {
                Text("Dagarna kan inte ändras efteråt, om inte tidrapporten avvisas.")
            }
            .task(id: month) { await load() }
            .refreshable { await load() }
            .errorAlert($error)
        }
    }

    private func shift(_ months: Int) {
        month = Calendar.current.date(byAdding: .month, value: months, to: month)!
    }

    private func load() async {
        let key = Day.string(month).prefix(7)
        do {
            data = try await session.get("absence/?month=\(key)")
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func delete(_ offsets: IndexSet) async {
        struct Ok: Decodable { let ok: Bool }
        guard let entries = data?.entries else { return }
        do {
            for entry in offsets.map({ entries[$0] }) {
                let _: Ok = try await session.post("absence/\(entry.id)/delete/", json: [:])
            }
        } catch {
            self.error = error.localizedDescription
        }
        await load()
    }

    private func submit() async {
        struct Message: Decodable { let message: String }
        busy = true
        defer { busy = false }
        do {
            let _: Message = try await session.post("absence/submit/", json: ["month": String(Day.string(month).prefix(7))])
        } catch {
            self.error = error.localizedDescription
        }
        await load()
    }
}

struct AbsenceEntryRow: View {
    let entry: AbsenceEntry

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(entry.absenceType).font(.headline)
                Text(entry.date).font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
            Text(entry.wholeDay ? "Hel dag" : "\(entry.hours ?? "") h").monospacedDigit()
        }
    }
}

struct TimeReportRow: View {
    let report: TimeReport

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(report.employee).font(.headline)
                Text("\(report.period) · \(report.entries.count) frånvaroposter")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            StatusBadge(status: report.status, text: report.statusDisplay)
        }
    }
}

/// Attestantens vy av en inskickad tidrapport.
struct TimeReportDetailView: View {
    let report: TimeReport

    var body: some View {
        List {
            Section {
                LabeledContent("Anställd", value: report.employee)
                LabeledContent("Period", value: report.period)
                LabeledContent("Status") { StatusBadge(status: report.status, text: report.statusDisplay) }
            }
            Section("Frånvaro") {
                ForEach(report.entries) { AbsenceEntryRow(entry: $0) }
                if report.entries.isEmpty {
                    Text("Ingen frånvaro under perioden.").foregroundStyle(.secondary)
                }
            }
            DecisionSection(kind: "tidrapport", id: report.id)
        }
        .navigationTitle("Tidrapport")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct NewAbsenceView: View {
    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    let range: ClosedRange<Date>
    let types: [AbsenceType]
    @State private var date: Date
    @State private var type: AbsenceType?
    @State private var hours = ""
    @State private var saving = false
    @State private var error: String?

    init(range: ClosedRange<Date>, types: [AbsenceType]) {
        self.range = range
        self.types = types
        _date = State(initialValue: min(max(Date(), range.lowerBound), range.upperBound))
    }

    var body: some View {
        NavigationStack {
            Form {
                DatePicker("Datum", selection: $date, in: range, displayedComponents: .date)
                Picker("Frånvaroart", selection: $type) {
                    Text("Välj").tag(AbsenceType?.none)
                    ForEach(types) { Text($0.name).tag(Optional($0)) }
                }
                if let type {
                    if type.isWholeDay {
                        Text("Räknas som dina schemalagda timmar den dagen.").font(.footnote).foregroundStyle(.secondary)
                    } else {
                        TextField("Antal timmar", text: $hours).keyboardType(.decimalPad)
                    }
                }
            }
            .navigationTitle("Ny frånvaro")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Avbryt") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Spara") { Task { await save() } }.disabled(saving || type == nil)
                }
            }
            .errorAlert($error)
        }
    }

    private func save() async {
        guard let type else { return }
        saving = true
        defer { saving = false }
        var json: [String: Any] = ["date": Day.string(date), "absence_type": type.id]
        if !type.isWholeDay {
            json["hours"] = hours.decimal
        }
        do {
            let _: AbsenceEntry = try await session.post("absence/", json: json)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
