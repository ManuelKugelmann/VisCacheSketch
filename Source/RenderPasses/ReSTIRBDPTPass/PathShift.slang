#include "Utils/Math/MathConstants.slangh"
import Scene.RaytracingInline;
import Rendering.Lights.EnvMapSampler;
import Rendering.Lights.EmissiveLightSampler;
import Utils.Debug.PixelDebug;
import Utils.Math.MathHelpers;
import Utils.Color.ColorHelpers;
import Utils.Geometry.GeometryHelpers;
__exported import PathGenerator;
import LightVertexCache;

extension PathGenerator {
    // shifts light paths with >1 bounce
    PathState<true> ShiftLightSubpath(const PathSample basePath, out PathVertex vertex) {
        PathState<true> s = InitializeLightPath<true, false>(basePath.mSuffix.mLightSubpath.mId, vertex, basePath.mSuffix.mLightSubpath.mFirstVertex);

        const uint lightVertexCount = basePath.mSuffix.mLightSubpath.mVertexCount + (basePath.HasFlag(PathFlags::eNonCausticLightPath) ? -1 : 0);

        while (any(s.throughput > 0) && s.pdfW > 0 && s.bounces + 2 < lightVertexCount && vertex.IsFinite()) {
            // for light paths: rcv is always the 2nd to last vertex
            s.rcv = vertex.Pack();
            s.rcvDirOut = vertex.GetDirIn();
            s.throughputAtRcv = s.throughput;
            s.pdfAtRcv = s.pdfW;
            s.prefixPdf = s.pdfW;
            s.prefixBounces = 0;
            s.rcvDiffuseBounces = 0;

            SampleNextVertex(s, vertex);

            s.rcvCos = abs(dot(s.lastVertex.normal, vertex.mVertex.mRayDirection));
            s.rcvDist = vertex.mVertex.mRayDistance;
            s.deltaRcv = !s.lastVertex.connectable;
        }

        return s;
    }

    // Returns the path state at the end of the prefix
    PathState<true> ShiftPrefix(const PathSample basePath, inout PathVertex vertex) {
        // initialize path state
        PathState<true> s = InitializeCameraPath<true>(basePath.mId, vertex);
        s.lightSubpathVertex = basePath.mSuffix.mLightSubpath.mFirstVertex;
        s.lightSubpathId     = basePath.mSuffix.mLightSubpath.mId;

        // trace the new prefix
        while (s.bounces < basePath.mPrefixBounces && any(s.throughput > 0)) {
            SampleNextVertex(s, vertex);
        }
        if (s.rcvFound || s.bounces != basePath.mPrefixBounces || s.diffuseBounces != basePath.mPrefixDiffuseBounces || !any(s.throughput > 0)) {
            print("Shift failed: Prefix length mismatch:", uint2(s.bounces, basePath.mPrefixBounces));
            s.Terminate();
            return s;
        }

        return s;
    }

    // Recomputes the suffix vertex's incoming ray based on vertex. Does not update the suffix's contribution.
    PathSuffix GetShiftedSuffixVertex(const PathVertex vertex, const PathSuffix baseSuffix, out Ray visibilityRay) {
        PathSuffix result = baseSuffix;

        const PathVertex suffixVertex = PathVertex(baseSuffix.mVertex);

        if (suffixVertex.IsFinite()) {
            result.mVertex.mRayDirection = suffixVertex.GetPosition() - vertex.GetPosition();
            result.mVertex.mRayDistance = length(result.mVertex.mRayDirection);
            result.mVertex.mRayDirection /= result.mVertex.mRayDistance;
            result.mVertex.mRayOrigin = vertex.ComputeRayOrigin(result.mVertex.mRayDirection);

            visibilityRay = Ray(
                result.mVertex.mRayOrigin,
                suffixVertex.ComputeRayOrigin(-result.mVertex.mRayDirection) - result.mVertex.mRayOrigin);
            visibilityRay.tMax = length(visibilityRay.dir);
            visibilityRay.dir /= visibilityRay.tMax;

            result.mCos = suffixVertex.GetCosN(result.mVertex.mRayDirection);
            result.mDist = result.mVertex.mRayDistance;
        } else {
            result.mVertex.mRayOrigin = vertex.ComputeRayOrigin(result.mVertex.mRayDirection);
            visibilityRay = Ray(result.mVertex.mRayOrigin, result.mVertex.mRayDirection);
        }

        return result;
    }

    // connect to suffix without shifting it. Assumes the path state is already at the end of the prefix
    PathSample ConnectToSuffix(inout PathState<true> s, inout PathVertex vertex, const PathSample basePath, const bool shiftToPrev) {
        const uint lightVertexCount = basePath.mSuffix.mLightSubpath.mVertexCount + (basePath.HasFlag(PathFlags::eNonCausticLightPath) ? -1 : 0);
        const uint cameraBounces = max(0, int(basePath.mBounces) - int(lightVertexCount));
        const float prefixPdf = s.pdfW;

        PathSample result = {};

        Ray visibilityRay;
        PathSuffix newSuffix = GetShiftedSuffixVertex(vertex, basePath.mSuffix, visibilityRay);

        if (newSuffix.mVertex.IsFinite()) {
            if (newSuffix.mCos < kMinCosTheta || (s.bounces < cameraBounces && newSuffix.mDist < mParams.mReconnectionDistance))
                return result;
        }

        // cache mis state at end of prefix, before connection
        RecursiveMisState prefixMis = s.mis;

        // advance to the reconnection vertex
        float prefixFwdPdfW, prefixRevPdfW, cameraPdfA, cameraCosOut;
        {
            if (Occluded(visibilityRay)) {
                print("Shift failed: suffix occluded", 0);
                return result;
            }

            cameraCosOut = vertex.GetCosN(newSuffix.mVertex.mRayDirection);
            if (cameraCosOut < kMinCosTheta)
                return result;

            if (basePath.HasFlag(PathFlags::eNonCausticLightPath)) {
                // for pure light paths, vertex is the primary hit since there is no prefix
                float3 toCamera = (shiftToPrev ? gScene.camera.data.prevPosW : gScene.camera.data.posW) - vertex.GetPosition();
                const float dist = length(toCamera);
                toCamera /= dist;

                float imageToSolidAngleFactor, cosAtCamera;
                if (shiftToPrev)
                    imageToSolidAngleFactor = GetPrevImageToSolidAngleFactor(-toCamera, cosAtCamera);
                else
                    imageToSolidAngleFactor = GetImageToSolidAngleFactor(-toCamera, cosAtCamera);

                const float cosToCamera =  vertex.GetCosN(toCamera);

                // Compute pdf conversion factor from image plane area to surface area
                cameraPdfA = imageToSolidAngleFactor * cosToCamera / sqr(dist);

                newSuffix.mCameraFwdPdf = 1;
                newSuffix.mCos = cameraCosOut;

                // get MIS state at new primary hit. TODO: skip visibility check in InitializeLightPath
                if (basePath.mBounces == 1) {
                    PathVertex tmp;
                    prefixMis = InitializeLightPath<true, true>(basePath.mSuffix.mLightSubpath.mId, tmp, basePath.mSuffix.mLightSubpath.mFirstVertex, vertex.mVertex).mis;
                }
            }

            SetNextVertex(s, vertex, PathVertex(newSuffix.mVertex));
            prefixFwdPdfW = s.lastVertex.scatterFwdPdfW;
            prefixRevPdfW = s.lastVertex.scatterRevPdfW;
            if (!any(s.throughput > 0)) {
                print("Shift failed: Zero reconnection reflectance", 0);
                return result;
            }

            if (basePath.HasFlag(PathFlags::eNonCausticLightPath)) {
                // divide out cosine term at primary hit for pure light paths
                s.throughput /= cameraCosOut;
            }
        }

        ReflectanceEvalData rcvF = {};
        if (s.bounces == basePath.mBounces) {
            newSuffix.mContribution = vertex.GetEmission();
            if (basePath.mSuffix.mLightSubpath.mVertexCount > 1) {
                newSuffix.mContribution *= vertex.GetCosN(vertex.GetDirIn());
            }
        } else {
            rcvF = vertex.EvaluateReflectance(s.sg, newSuffix.mDirOut, false);
            if (s.bounces > cameraBounces) {
                // divide out cosine term if the rcv was originally on the light subpath
                float fac = 1 / vertex.GetCosN(newSuffix.mDirOut);
                if (basePath.HasFlag(PathFlags::eNonCausticLightPath))
                    fac *= vertex.GetCosN(vertex.GetDirIn()); // include cosine term towards primary hit for pure light paths
                rcvF.mReflectance *= fac;
            }
            s.throughput *= rcvF.mReflectance;
        }

        float misWeight = basePath.mMisWeight;

        // compute new MIS weight for the shifted path
        #if USE_RECONNECTION_MIS
        if (gUseReconnectionMIS && !DebugDisableMIS()) {
            misWeight = 0;
            if (basePath.HasFlag(PathFlags::eNonCausticLightPath) && gBidirectional) {
                RecursiveMisState mis;
                float cosIn = s.lastVertex.HasNormal() ? abs(dot(s.lastVertex.normal, vertex.GetDirIn())) : 1;
                if (basePath.mBounces == 1) {
                    // single-bounce pure light path. In this case, prefixMis is assigned after the BSDF is evaluated above
                    mis = prefixMis;
                } else {
                    // advance the cached MIS state at the reconnection vertex to the primary hit
                    mis = basePath.mSuffix.mMisEvalArgs.lightSubpathMis;

                    // note: must swap forward and reverse PDFs since light tracing would have evaluated the reverse BSDF
                    DirectionSampleData r = {};
                    r.mFwdPdfW = rcvF.mRevPdfW;
                    r.mRevPdfW = rcvF.mFwdPdfW;
                    r.mLobeType = 0;
                    mis.ProcessDirection(r, vertex.GetCosN(vertex.GetDirIn()), true);
                    mis.ProcessRay(vertex.mVertex.mRayDistance, cosIn);
                }

                misWeight = mis.EvalLightTraceMIS(prefixFwdPdfW, cameraPdfA);
            } else {
                RecursiveMisState mis = s.mis;

                if (s.bounces == basePath.mBounces) {
                    // rcv is last path vertex
                    GetLightSamplePdf(
                        vertex,
                        s.lastVertex.position,
                        s.lastVertex.normal,
                        s.lastVertex.upperHemisphereOnly,
                        newSuffix.mMisEvalArgs.emissionPdfW,
                        newSuffix.mMisEvalArgs.directPdfW,
                        newSuffix.mMisEvalArgs.directPdfA );

                    newSuffix.mMisEvalArgs.cameraScatterFwdPdfW = prefixFwdPdfW;
                    newSuffix.mMisEvalArgs.cameraScatterRevPdfW = prefixRevPdfW;
                    newSuffix.mMisEvalArgs.cosCam = abs(dot(s.lastVertex.normal, vertex.mVertex.mRayDirection));
                    newSuffix.mMisEvalArgs.cosLight = vertex.GetCosN(vertex.mVertex.mRayDirection);
                    if (basePath.mSuffix.mLightSubpath.mVertexCount == 1)
                        mis = prefixMis; // NEE path: need MIS state before connection
                } else if (s.bounces > cameraBounces) {
                    // rcv is on the light subpath
                    mis = prefixMis;
                    newSuffix.mMisEvalArgs.lightScatterFwdPdfW = rcvF.mRevPdfW;
                    newSuffix.mMisEvalArgs.lightScatterRevPdfW = rcvF.mFwdPdfW;
                    newSuffix.mMisEvalArgs.cameraScatterFwdPdfW = prefixFwdPdfW;
                    newSuffix.mMisEvalArgs.cameraScatterRevPdfW = prefixRevPdfW;
                    newSuffix.mMisEvalArgs.cosCam = cameraCosOut;
                    newSuffix.mMisEvalArgs.cosLight = vertex.GetCosN(vertex.GetDirIn());
                    newSuffix.mMisEvalArgs.invDist2 = 1/sqr(vertex.mVertex.mRayDistance);
                } else if (s.bounces == cameraBounces) {
                    // rcv is last camera subpath vertex. mis is up to date. dont need to do anything.
                } else {
                    // rcv is on camera subpath. advance mis to end of camera subpath
                    basePath.mSuffix.mMisEvalArgs.reconnectionMis.Apply( mis, rcvF.mFwdPdfW, rcvF.mRevPdfW, cameraBounces == (basePath.mPrefixBounces + 2) );
                }

                // Eval MIS weight according to technique
                if (basePath.mSuffix.mLightSubpath.mVertexCount == 0) {
                    misWeight = mis.EvalCameraTraceMIS(
                        newSuffix.mMisEvalArgs.cameraScatterFwdPdfW,
                        newSuffix.mMisEvalArgs.directPdfA,
                        newSuffix.mMisEvalArgs.directPdfW,
                        newSuffix.mMisEvalArgs.emissionPdfW );
                } else if (basePath.mSuffix.mLightSubpath.mVertexCount == 1) {
                    misWeight = mis.EvalDirectLightMIS(
                        newSuffix.mMisEvalArgs.directPdfW,
                        newSuffix.mMisEvalArgs.emissionPdfW,
                        { float3(0), newSuffix.mMisEvalArgs.cameraScatterFwdPdfW, newSuffix.mMisEvalArgs.cameraScatterRevPdfW },
                        newSuffix.mMisEvalArgs.cosCam,
                        newSuffix.mMisEvalArgs.cosLight );
                } else if (gBidirectional) {
                        misWeight = mis.EvalVertexConnectionMIS(
                            newSuffix.mMisEvalArgs.lightSubpathMis,
                            { float3(0), newSuffix.mMisEvalArgs.lightScatterFwdPdfW, newSuffix.mMisEvalArgs.lightScatterRevPdfW },
                            { float3(0), newSuffix.mMisEvalArgs.cameraScatterFwdPdfW, newSuffix.mMisEvalArgs.cameraScatterRevPdfW },
                            newSuffix.mMisEvalArgs.cosCam,
                            newSuffix.mMisEvalArgs.cosLight,
                            newSuffix.mMisEvalArgs.invDist2 );
                }
            }

            print("    mis base, shifted, error", float3(basePath.mMisWeight, misWeight, abs((misWeight - basePath.mMisWeight) / basePath.mMisWeight)));
            print("    bounces, cameraBounces, prefixBounces, s.bounces", uint4(basePath.mBounces, cameraBounces, basePath.mPrefixBounces, s.bounces));
        }
        #endif

        result = basePath;
        result.mContribution = s.throughput * newSuffix.mContribution;
        result.mMisWeight = misWeight;
        result.mPrefixPdf = prefixPdf;
        result.mSuffix = newSuffix;

        return result;
    }

    // Shift and connect to a suffix. Assumes the path state is already at the end of the prefix, and the light subpath (if any) has been already shifted.
    PathSample ShiftSuffix(inout PathState<true> s, inout PathVertex vertex, const PathSample basePath, const LightSubpathVertex shiftedLightVertex) {
        const uint lightVertexCount = basePath.mSuffix.mLightSubpath.mVertexCount + (basePath.HasFlag(PathFlags::eNonCausticLightPath) ? -1 : 0);
        const uint cameraBounces = max(0, int(basePath.mBounces) - int(lightVertexCount));

        PathSample result = {};

        // advance to the 1st suffix vertex (the reconnection vertex)
        if (s.bounces < cameraBounces) {
            Ray visibilityRay;
            const PathSuffix newSuffix = GetShiftedSuffixVertex(vertex, basePath.mSuffix, visibilityRay);
            if (newSuffix.mVertex.IsFinite() && (newSuffix.mDist < mParams.mReconnectionDistance || newSuffix.mCos < kMinCosTheta)) {
                print("Shift failed: reconnection G", 0);
                return result;
            }

            const PathVertex rcv = PathVertex(newSuffix.mVertex);
            if (Occluded(visibilityRay)) {
                print("Shift failed: Suffix occluded", float2(visibilityRay.tMax, newSuffix.mCos));
                return result;
            }

            SetNextVertex(s, vertex, rcv);
            if (!any(s.throughput > 0) || !(s.pdfW > 0)) {
                print("Shift failed: zero prefix reflectance", 0);
                return result;
            }

            if (!s.rcvFound) {
                print("Shift failed: Rcv mismatch", 0);
                return result;
            }
        }

        // advance to the 2nd suffix vertex
        if (s.bounces < cameraBounces) {
            SetNextVertex(s, vertex, PathVertex(TraceRay(Ray(vertex.ComputeRayOrigin(basePath.mSuffix.mDirOut), basePath.mSuffix.mDirOut))));
            if (!any(s.throughput > 0) || !(s.pdfW > 0)) {
                print("Shift failed: zero rcv reflectance", 0);
                return result;
            }
        }

        // advance to the last camera vertex
        while (s.bounces < cameraBounces && any(s.throughput > 0) && vertex.IsFinite()) {
            SampleNextVertex(s, vertex);
        }
        if (s.bounces != cameraBounces || !any(s.throughput > 0) || !(s.pdfW > 0)) {
            print("Shift failed: Camera subpath length mismatch:", uint2(s.bounces, cameraBounces));
            s.Terminate();
            return result;
        }

        // perform the original sampling technique

        float w;
        if (basePath.mSuffix.mLightSubpath.mVertexCount == 0) {
            result = EvalLightContribution(s, vertex, w);
        } else {
            if (!vertex.IsConnectable()) {
                print("Shift failed: Unconnectable camera subpath vertex", uint2(vertex.IsFinite(), vertex.mMaterial.getLobeTypes(vertex.mShadingData)));
                return result;
            }
            if ((gBidirectional || gSampleDirectLight) && basePath.mSuffix.mLightSubpath.mVertexCount == 1) {
                result = ConnectToLight(s, vertex, w);
            } else if (gBidirectional && basePath.mSuffix.mLightSubpath.mVertexCount > 1) {
                result = ConnectToLightSubpath(s, vertex, shiftedLightVertex, w);
            }
        }

        return result;
    }
}

// Top-level

// Shift a path to a new primary vertex. For pure random replay light paths, newPixel is set to the pixel the last light subpath vertex lands in.
PathSample ShiftPath(const PathSample basePath, const PackedPathVertex newPrimaryHit, out int2 newPixel, out float jacobian, const bool shiftToPrev = false) {
    jacobian = 0;
    newPixel = -1;
    PathSample result = {};

    const bool hasLightSubpath = gPathGenerator.gBidirectional && (
        (basePath.HasSuffix() && basePath.mSuffix.mLightSubpath.mVertexCount > 1) ||
        (!gPathGenerator.gDisableCameraConnection && basePath.HasFlag((PathFlags)((uint)PathFlags::eNonCausticLightPath|(uint)PathFlags::eCausticLightPath))) );

    // Shift the light subpath

    LightSubpathVertex shiftedLightVertex = {};
    if (hasLightSubpath) {
        if (basePath.HasFlag(PathFlags::eCausticLightPath) && !gPathGenerator.gShiftSuffixes && !gPathGenerator.gDisableCameraConnection) {
            // Without suffix shifts, caustic paths are unshiftable
            return result;
        }

        if (gPathGenerator.gShiftSuffixes) {
            // trace light subpath, so that vertex is the end of the light subpath
            PathVertex vertex;
            PathGenerator.PathState<true> s;
            if (!gPathGenerator.gDisableCameraConnection && basePath.HasFlag(PathFlags::eNonCausticLightPath) && basePath.mBounces == 1) {
                // for pure light paths with 1 bounce, we need to modify the initial sampling
                // so that newPrimaryHit is the 2nd vertex
                s = gPathGenerator.InitializeLightPath<true, true>(basePath.mSuffix.mLightSubpath.mId, vertex, basePath.mSuffix.mLightSubpath.mFirstVertex, newPrimaryHit);
            } else {
                s = gPathGenerator.ShiftLightSubpath(basePath, vertex);
                if (!vertex.IsFinite())
                    s.Terminate();
            }
            if (!any(s.throughput > 0) || !(s.pdfW > 0)) {
                print("Shift failed: Light subpath shift failed", s.throughput);
                return result;
            }

            // light trace shift
            if (!gPathGenerator.gDisableCameraConnection) {
                if (basePath.HasFlag(PathFlags::eCausticLightPath)) {
                    // Connect caustic paths to the camera directly
                    float w;
                    result = gPathGenerator.ConnectToCamera(s, vertex, newPixel, w, true, shiftToPrev);
                    if (!result.IsValid()) {
                        print("Shift failed: gPathGenerator.ConnectToCamera failed", 0);
                        result = {};
                        return result;
                    }

                    if (!result.HasFlag(PathFlags::eCausticLightPath)) {
                        print("Shift failed: Non-caustic result", 0);
                        result = {};
                        return result;
                    }

                    jacobian = basePath.mSuffix.mLightSubpath.mPdf / result.mSuffix.mLightSubpath.mPdf;
                    jacobian *= basePath.mSuffix.mCameraFwdPdf / result.mSuffix.mCameraFwdPdf; // includes camera cosine term
                    return result;
                } else if (basePath.HasFlag(PathFlags::eNonCausticLightPath)) {
                    // connect non-caustic pure light paths to the new primary hit

                    if (basePath.mBounces > 1) {
                        PathVertex v = PathVertex(newPrimaryHit);
                        float3 to_v = v.GetPosition() - vertex.GetPosition();
                        const float dist = length(to_v);
                        to_v /= dist;

                        if (!vertex.IsConnectable() || !v.IsConnectable()) {
                            print("Shift failed: Unconnectable light subpath", bool2(vertex.IsConnectable(), v.IsConnectable()));
                            return result;
                        }

                        // advance to primary hit
                        {
                            const float3 rayOrigin = vertex.ComputeRayOrigin(to_v);
                            Ray visibilityRay = Ray(rayOrigin, v.ComputeRayOrigin(-to_v) - rayOrigin);
                            visibilityRay.tMax = length(visibilityRay.dir);
                            visibilityRay.dir /= visibilityRay.tMax;
                            if (gPathGenerator.Occluded(visibilityRay)) {
                                print("Shift failed: Light subpath occluded", 0);
                                return result;
                            }

                            // for light paths: rcv is always the 2nd to last vertex
                            s.rcv = vertex.Pack();
                            s.rcvDirOut = vertex.GetDirIn();
                            s.throughputAtRcv = s.throughput;
                            s.pdfAtRcv = s.pdfW;
                            s.prefixPdf = s.pdfW;
                            s.prefixBounces = 0;
                            s.rcvDiffuseBounces = 0;

                            gPathGenerator.SetNextVertex(s, vertex, PathVertex(PackedPathVertex(Ray(rayOrigin, to_v), HitInfo(newPrimaryHit.mPackedHit), dist)));

                            s.rcvCos = abs(dot(s.lastVertex.normal, vertex.mVertex.mRayDirection));
                            s.rcvDist = vertex.mVertex.mRayDistance;
                            s.deltaRcv = false;
                        }
                    }

                    int2 offsetPixel;
                    float w;
                    result = gPathGenerator.ConnectToCamera(s, vertex, offsetPixel, w, false, shiftToPrev);
                    if (!result.IsValid()) {
                        print("Shift failed: gPathGenerator.ConnectToCamera failed", 0);
                        result = {};
                        return result;
                    }

                    jacobian = basePath.mSuffix.mLightSubpath.mPdf / result.mSuffix.mLightSubpath.mPdf;
                    jacobian *= result.mSuffix.mCos / basePath.mSuffix.mCos;
                    if (basePath.mSuffix.mVertex.IsFinite()) jacobian *= sqr(basePath.mSuffix.mDist / result.mSuffix.mDist);
                    jacobian *= basePath.mSuffix.mCameraFwdPdf / result.mSuffix.mCameraFwdPdf; // includes camera cosine term
                    return result;
                }
            }

            // store light subpath vertex for reconnection
            shiftedLightVertex = gPathGenerator.PackLightSubpathVertex(s, vertex);
        }
    }

    // Shift the camera subpath
    {
        PathVertex vertex = PathVertex(newPrimaryHit);
        PathGenerator.PathState<true> s = gPathGenerator.ShiftPrefix(basePath, vertex);
        if (!any(s.throughput > 0)) {
            print("Shift failed: Invalid prefix", 0);
            return result;
        }

        if (basePath.HasSuffix() || hasLightSubpath) {
            if (!vertex.IsConnectable()) {
                print("Shift failed: Non reconnectable prefix", 0);
                return result;
            }

            if (gPathGenerator.gShiftSuffixes) {
                // shift the suffix and apply the original sampling technique
                result = gPathGenerator.ShiftSuffix(s, vertex, basePath, shiftedLightVertex);
            } else {
                // reconnect to the suffix vertex
                result = gPathGenerator.ConnectToSuffix(s, vertex, basePath, shiftToPrev);
            }
        } else {
            // pure random replay camera path, no suffix
            float w;
            result = gPathGenerator.EvalLightContribution(s, vertex, w);
        }
    }

    if (!result.IsValid()) {
        print("Shift failed: Invalid result", float4(result.mContribution, result.mPrefixPdf));
        return {};
    }

    // random replay jacobian
    jacobian = basePath.mPrefixPdf / result.mPrefixPdf;

    if (hasLightSubpath || (basePath.HasSuffix() && basePath.mSuffix.mVertex.IsFinite())) {
        // reconnection jacobian
        jacobian *= result.mSuffix.mCos / basePath.mSuffix.mCos;
        if (basePath.mSuffix.mVertex.IsFinite()) jacobian *= sqr(basePath.mSuffix.mDist / result.mSuffix.mDist);

        // suffix jacobian (includes light subpath jacobian)
        jacobian *= basePath.mSuffix.mCameraFwdPdf / result.mSuffix.mCameraFwdPdf;
    }

    return result;
}

// Faster version of ShiftPath with just the light subpath random replay code path
PathSample ShiftCausticPath(const PathSample basePath, out int2 newPixel, out float jacobian, const bool shiftToPrev = false) {
    jacobian = 0;
    newPixel = -1;
    PathSample result = {};

    if (!basePath.HasSuffix() || !basePath.HasFlag(PathFlags::eCausticLightPath))
        return result;

    // trace light subpath, so that vertex is the end of the light subpath
    PathVertex vertex;
    PathGenerator.PathState<true> s = gPathGenerator.ShiftLightSubpath(basePath, vertex);
    if (s.bounces + 2 != basePath.mSuffix.mLightSubpath.mVertexCount || !vertex.IsFinite())
        s.Terminate();

    if (!any(s.throughput > 0) || !(s.pdfW > 0)) {
        print("Shift failed: Light subpath shift failed", s.throughput);
        return result;
    }

    // Connect caustic paths to the camera directly
    float w;
    result = gPathGenerator.ConnectToCamera(s, vertex, newPixel, w, true, shiftToPrev);
    if (!result.IsValid()) {
        print("Shift failed: gPathGenerator.ConnectToCamera failed", 0);
        result = {};
        return result;
    }

    if (!result.HasFlag(PathFlags::eCausticLightPath)) {
        print("Shift failed: Non-caustic result", 0);
        result = {};
        return result;
    }

    jacobian = basePath.mSuffix.mLightSubpath.mPdf / result.mSuffix.mLightSubpath.mPdf;
    jacobian *= basePath.mSuffix.mCameraFwdPdf / result.mSuffix.mCameraFwdPdf; // includes camera reconnection and cosine^3 terms
    return result;
}
