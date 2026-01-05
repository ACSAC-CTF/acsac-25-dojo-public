#!/bin/bash
# Script to patch binary to use local ld-linux-x86-64.so.2 and libc.so.6

set -e

BINARY="manaiakalani"

if [ ! -f "$BINARY" ]; then
    echo "Error: $BINARY not found in current directory"
    exit 1
fi

if [ ! -f "ld-linux-x86-64.so.2" ]; then
    echo "Error: ld-linux-x86-64.so.2 not found in current directory"
    exit 1
fi

if [ ! -f "libc.so.6" ]; then
    echo "Error: libc.so.6 not found in current directory"
    exit 1
fi

echo "Patching $BINARY to use local libraries..."

# Set the interpreter to use local ld-linux-x86-64.so.2
patchelf --set-interpreter ./ld-linux-x86-64.so.2 "$BINARY"

# Set rpath to $ORIGIN so it looks for libc.so.6 in current directory
patchelf --set-rpath '$ORIGIN' "$BINARY"

echo "Verifying patch..."
echo "Interpreter:"
readelf -l "$BINARY" | grep -A1 interpreter | grep "Requesting program interpreter" | awk '{print $4}'

echo ""
echo "Library resolution:"
LD_LIBRARY_PATH=. ldd "$BINARY" | grep -E "libc|ld-linux"

echo ""
echo "✓ Binary patched successfully!"
echo "  - Interpreter: ./ld-linux-x86-64.so.2"
echo "  - libc.so.6 will be loaded from current directory"

