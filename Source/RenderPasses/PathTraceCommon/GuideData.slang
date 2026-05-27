/***************************************************************************
 # GuideData.slang — guide data struct shared by every NRD-capable PT
 # lineage plugin (PathTracerX + ReSTIRDIPass + ReSTIRDIReferencePass +
 # ReSTIRNEEPass). Pure packed-struct, no plugin-local imports.
 *************************************************************************/
import Utils.Math.PackedFormats;
import Utils.Math.FormatConversion;

static const float kEnvMapDepth = 100000000.0f; // Same constant as defined in GBufferRT.slang

/** Struct holding guide data for denoising.
*/
struct GuideData
{
    uint4 data;
    float3 reflectionPos;
    float dummy;

    float3 getAlbedo()
    {
        return unpackR11G11B10(data[0]);
    }

    [mutating] void setAlbedo(float3 albedo)
    {
        data[0] = packR11G11B10(albedo);
    }

    float3 getGuideNormal()
    {
        return decodeNormal2x16(data[1]);
    }

    [mutating] void setGuideNormal(float3 normal)
    {
        data[1] = encodeNormal2x16(normal);
    }

    float3 getSpecularAlbedo()
    {
        return unpackR11G11B10(data[2]);
    }

    [mutating] void setSpecularAlbedo(float3 specular)
    {
        data[2] = packR11G11B10(specular);
    }

    float3 getIndirectAlbedo()
    {
        return unpackR11G11B10(data[3]);
    }

    [mutating] void setIndirectAlbedo(float3 albedo)
    {
        data[3] = packR11G11B10(albedo);
    }

    float3 getReflectionPos()
    {
        return reflectionPos;
    }

    [mutating] void setReflectionPos(float3 pos)
    {
        reflectionPos = pos;
    }
};
