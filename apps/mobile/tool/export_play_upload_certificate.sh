#!/usr/bin/env bash
set -euo pipefail

tool_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile_dir="$(cd "$tool_dir/.." && pwd)"
properties_path="$mobile_dir/android/key.properties"

if [[ ! -f "$properties_path" ]]; then
  echo "android/key.properties est absent." >&2
  exit 1
fi

declare storePassword keyAlias storeFile
while IFS='=' read -r key value; do
  case "$key" in
    storePassword) storePassword="$value" ;;
    keyAlias) keyAlias="$value" ;;
    storeFile) storeFile="$value" ;;
  esac
done <"$properties_path"

keystore_path="$mobile_dir/android/$storeFile"
output_dir="$mobile_dir/build/play"
output_path="$output_dir/upload-certificate.pem"
mkdir -p "$output_dir"

if [[ -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/keytool" ]]; then
  keytool_bin="$JAVA_HOME/bin/keytool"
elif [[ -x "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home/bin/keytool" ]]; then
  keytool_bin="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home/bin/keytool"
else
  keytool_bin="$(command -v keytool)"
fi

"$keytool_bin" -exportcert -rfc \
  -keystore "$keystore_path" \
  -storepass "$storePassword" \
  -alias "$keyAlias" \
  -file "$output_path"

echo "Certificat public exporté : $output_path"
