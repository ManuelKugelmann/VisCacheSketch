/***************************************************************************
 # ColorType.slang — per-pixel color storage struct.
 #
 # Shared by every Falcor-PT-lineage plugin (PathTracerX + ReSTIRDIPass +
 # ReSTIRDIReferencePass + ReSTIRNEEPass). Each consumer plugin injects
 # the `COLOR_FORMAT` preprocessor macro from its C++ side
 # (`defines.add("COLOR_FORMAT", ...)`); this file just dispatches on it.
 # No `import Params;` needed — the macro is set at compile-unit scope.
 *************************************************************************/
import Utils.Math.PackedFormats;

struct ColorType
{
#if COLOR_FORMAT == 0 /* ColorFormat::RGBA32F */
    float4 data;

    float3 get()
    {
        return data.rgb;
    }

    [mutating] void set(float3 color)
    {
        data = float4(color, 1.f);
    }

#elif COLOR_FORMAT == 1 /* ColorFormat::LogLuvHDR */
    uint data;

    float3 get()
    {
        return decodeLogLuvHDR(data);
    }

    [mutating] void set(float3 color)
    {
        data = encodeLogLuvHDR(color);
    }

#else
#error Invalid COLOR_FORMAT
#endif
};
