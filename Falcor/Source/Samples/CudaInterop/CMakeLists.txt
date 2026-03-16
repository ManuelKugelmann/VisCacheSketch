if(NOT FALCOR_HAS_CUDA)
    return()
endif()

add_falcor_executable(CudaInterop)

target_sources(CudaInterop PRIVATE
    CopySurface.cu
    CopySurface.h
    CudaInterop.cpp
    CudaInterop.h
)

set_target_properties(CudaInterop PROPERTIES CUDA_SEPARABLE_COMPILATION ON)

if(MSVC)
    # Suppress C4100 in CUDA-generated device-link registration files
    # (unreferenced 'prelinked_fatbinc' parameter).
    target_compile_options(CudaInterop PRIVATE /wd4100)
    # CUDA runtime links LIBCMT (static CRT); Falcor uses dynamic CRT (MSVCRT).
    target_link_options(CudaInterop PRIVATE /NODEFAULTLIB:LIBCMT)
endif()

target_source_group(CudaInterop "Samples")
