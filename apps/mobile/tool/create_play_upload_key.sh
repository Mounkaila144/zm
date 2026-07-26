#!/usr/bin/env bash
set -euo pipefail

tool_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mobile_dir="$(cd "$tool_dir/.." && pwd)"
android_dir="$mobile_dir/android"
keystore_path="$android_dir/upload-keystore.jks"
properties_path="$android_dir/key.properties"

if [[ -e "$keystore_path" || -e "$properties_path" ]]; then
  echo "La clé ou key.properties existe déjà. Aucun fichier n'a été remplacé." >&2
  exit 1
fi

if [[ -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/keytool" ]]; then
  keytool_bin="$JAVA_HOME/bin/keytool"
elif [[ -x "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home/bin/keytool" ]]; then
  keytool_bin="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home/bin/keytool"
else
  keytool_bin="$(command -v keytool)"
fi

password="$(openssl rand -hex 24)"
umask 077

"$keytool_bin" -genkeypair \
  -v \
  -keystore "$keystore_path" \
  -storetype JKS \
  -storepass "$password" \
  -keypass "$password" \
  -alias zarma-upload \
  -keyalg RSA \
  -keysize 4096 \
  -validity 10000 \
  -dname "CN=PTR Niger, O=PTR Niger, L=Niamey, ST=Niamey, C=NE"

cat >"$properties_path" <<EOF
storePassword=$password
keyPassword=$password
keyAlias=zarma-upload
storeFile=upload-keystore.jks
EOF

echo "Clé d'envoi créée : $keystore_path"
echo "Configuration locale créée : $properties_path"
echo "Sauvegardez immédiatement ces deux fichiers dans un coffre-fort sécurisé."
