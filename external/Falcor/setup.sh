#!/bin/sh

# This script is fetching all dependencies via packman.

if [ "$OSTYPE" = "msys" ]; then
    echo "Do not use "$0" on Windows, use setup.bat instead."
    exit 1
fi

BASE_DIR=$(dirname "$0")
PACKMAN=${BASE_DIR}/tools/packman/packman
PLATFORM=linux-x86_64

echo "Fetching pinned submodules ..."

if ! [ -x "$(command -v git)" ]; then
    echo "Cannot find git on PATH! Please initialize submodules manually and rerun."
    exit 1
else
    grep -v '^#' "${BASE_DIR}/external/submodules.txt" | while read -r name url sha; do
        [ -z "$name" ] && continue
        dir="${BASE_DIR}/external/$name"
        if [ ! -f "$dir/CMakeLists.txt" ] && [ ! -f "$dir/imgui.h" ]; then
            echo "  Fetching $name @ ${sha:0:10}"
            rm -rf "$dir"
            mkdir -p "$dir"
            git -C "$dir" init -q
            git -C "$dir" remote add origin "$url"
            git -C "$dir" fetch --depth 1 origin "$sha"
            git -C "$dir" checkout FETCH_HEAD -q
        else
            echo "  $name already present, skipping"
        fi
    done
fi

echo "Fetching dependencies ..."

${PACKMAN} pull --platform ${PLATFORM} ${BASE_DIR}/dependencies.xml
if [ $? -ne 0 ]; then
    echo "Failed to fetch dependencies!"
    exit 1
fi

if [ ! -d ${BASE_DIR}/.vscode ]; then
    echo "Setting up VS Code workspace ..."
    cp -rp ${BASE_DIR}/.vscode-default ${BASE_DIR}/.vscode
fi

# HACK: Copy libnvtt.so.30106 to libnvtt.so so we can use it in our build.
# This changes the actual packman package, but for now, this is the easiest solution.
echo "Patching NVTT package ..."
cp -fp ${BASE_DIR}/external/packman/nvtt/libnvtt.so.30106 ${BASE_DIR}/external/packman/nvtt/libnvtt.so

exit 0
