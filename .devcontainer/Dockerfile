# VisCacheSketch devcontainer — Ubuntu 22.04 + NVIDIA CUDA + Vulkan
# Builds Falcor (linux-gcc-ci preset) and runs Mogwai with Vulkan backend.
# Requires: Docker Desktop with GPU support (--gpus all) via WSL2.

FROM nvidia/cuda:12.2.2-devel-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive

# Core build tools + Vulkan + X11/display
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc-12 g++-12 \
    cmake \
    ninja-build \
    git \
    git-lfs \
    python3 python3-pip python3-venv \
    curl wget unzip \
    # Vulkan SDK + runtime
    libvulkan-dev vulkan-tools mesa-vulkan-drivers \
    # X11 / display (for non-headless Mogwai)
    libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
    libxext-dev libxkbcommon-dev libwayland-dev \
    libgl1-mesa-dev libegl1-mesa-dev \
    # Misc
    pkg-config \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set GCC 12 as default
RUN update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 100 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-12 100

# Vulkan ICD loader — NVIDIA runtime provides the actual ICD
ENV VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json

# Packman expects these
ENV HOME=/home/vscode
RUN useradd -ms /bin/bash vscode

USER vscode
WORKDIR /workspaces/VisCacheSketch
