#!/usr/bin/env bash
# seal.sh — seal a bootstrap credential to the machine's TPM2 PCR state via systemd-creds.
#
# Usage:  ./seal.sh <plaintext-value> [credential-name]
#
# Wraps `systemd-creds encrypt` so the sealed blob can only be decrypted on this machine
# with the current PCR measurements. The output lives at run/<name>.cred — an opaque blob
# that is safe to store on disk (it's ciphertext bound to silicon).
#
# The plaintext value here is the BOOTSTRAP SECRET (e.g. an OpenBao token). In this demo
# it's an obvious fake: S3cr3t-Pg-Pass.
set -euo pipefail

PLAINTEXT="${1:?Usage: $0 <plaintext-value> [credential-name]}"
NAME="${2:-bao-token}"

HERE="$(cd "$(dirname "$0")" && pwd)"
RUN="$HERE/run"
mkdir -p "$RUN"

SEALED="$RUN/${NAME}.cred"

# Seal to TPM2 PCR measurements — the credential can only be unsealed on this machine
# with the same boot state. If swtpm is in use (demo mode), systemd-creds will find the
# TPM2 device at the path set by SYSTEMD_CREDENTIAL_SECRET or via /dev/tpmrm0.
echo -n "$PLAINTEXT" | systemd-creds encrypt --with-key=tpm2 --name="$NAME" - "$SEALED"

echo "-> sealed '$NAME' to TPM2 PCR state: $SEALED ($(stat -c%s "$SEALED") bytes)"
echo "   (the plaintext never touches disk — only the sealed blob is stored)"
