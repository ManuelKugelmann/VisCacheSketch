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
    # Must use generator expressions: bare /wd4100 is misinterpreted as a
    # filename by nvcc >= 12.9, causing "single input file required" errors.
    target_compile_options(CudaInterop PRIVATE
        $<$<COMPILE_LANGUAGE:CXX>:/wd4100>
        $<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler=/wd4100>
    )
    # CUDA runtime links LIBCMT (static CRT); Falcor uses dynamic CRT (MSVCRT).
    target_link_options(CudaInterop PRIVATE /NODEFAULTLIB:LIBCMT)
endif()

target_source_group(CudaInterop "Samples")
