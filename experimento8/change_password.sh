#!/bin/bash

# change_password.sh
# Script to change the password in fechadura.py by storing only its SHA-256 hash

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <new_password>"
    exit 1
fi

NEW_PASSWORD="$1"
TARGET_DIR="$(dirname "$0")"
TARGET_FILE="$TARGET_DIR/fechadura.py"

if [ ! -f "$TARGET_FILE" ]; then
    echo "Error: Cannot find $TARGET_FILE"
    exit 1
fi

python3 -c '
import sys
import re
import hashlib

new_password = sys.argv[1]
target_file = sys.argv[2]

# Compute SHA-256 hash
new_hash = hashlib.sha256(new_password.encode()).hexdigest()

try:
    with open(target_file, "r") as f:
        content = f.read()
        
    # Remove the comment containing the plaintext password
    content = re.sub(
        r"# Senha padrão(.*?): \"[^\"]*\"(.*)",
        r"# Senha padrão armazenada como hash SHA-256\n",
        content
    )
    # Also handle if it was already changed to not contain plaintext
    content = re.sub(
        r"# Senha padrão armazenada como hash SHA-256.*\n(# Senha padrão)?",
        r"# Senha padrão armazenada como hash SHA-256\n",
        content
    )
    
    # Generic replace for the comment (just in case the above doesnt match perfectly)
    content = re.sub(
        r"# Senha padrão:.*",
        r"# Senha armazenada como hash SHA-256",
        content
    )

    # Replace the DEFAULT_PASSWORD_HASH line
    content = re.sub(
        r"DEFAULT_PASSWORD_HASH = [^\n]+",
        f"DEFAULT_PASSWORD_HASH = \"{new_hash}\"",
        content
    )

    with open(target_file, "w") as f:
        f.write(content)
        
    print(f"Password successfully updated in {target_file} (stored as hash)")
except Exception as e:
    print(f"Error updating file: {e}")
    sys.exit(1)
' "$NEW_PASSWORD" "$TARGET_FILE"
