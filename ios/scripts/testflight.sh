#!/bin/sh
# Arkiverar ExpenseVibe och laddar upp till TestFlight (som SaldoVibes ios/scripts/testflight.sh).
#
# Kräver: Xcode inloggat (Xcode → Settings → Accounts) med ett Apple-ID i team 7MV2FUVY65 och
# en app i App Store Connect med bundle-id se.damadev.ExpenseVibe. Automatisk signering skapar
# distributionscertifikat och profil första gången.
#
# Byggnumret blir aktuell minut (yyyymmddHHMM) så att varje uppladdning är unik.
set -eu
cd "$(dirname "$0")/.."
BUILD=${BUILD_NUMBER:-$(date +%Y%m%d%H%M)}
ARCHIVE=${ARCHIVE_PATH:-build/ExpenseVibe.xcarchive}
LOG=build/testflight.log
mkdir -p build

step() {
  # Kör ett xcodebuild-steg tyst; vid fel visas felen, annars sista raden.
  name=$1; shift
  if "$@" > "$LOG" 2>&1; then
    tail -1 "$LOG"
  else
    echo "$name misslyckades – ur $LOG:" >&2
    grep -E "error:|error |ERROR" "$LOG" | sort -u | head -20 >&2
    exit 1
  fi
}

xcodegen generate --quiet

step "Arkivering" xcodebuild archive \
  -project ExpenseVibe.xcodeproj -scheme ExpenseVibe -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
  -allowProvisioningUpdates CURRENT_PROJECT_VERSION="$BUILD"

step "Uppladdning" xcodebuild -exportArchive \
  -archivePath "$ARCHIVE" -exportOptionsPlist ExportOptions.plist -exportPath build/export \
  -allowProvisioningUpdates

echo "Build $BUILD laddades upp. Den dyker upp under TestFlight i App Store Connect efter bearbetning (några minuter)."
