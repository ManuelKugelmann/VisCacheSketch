/***************************************************************************
 # Copyright (c) 2022, Daqi Lin.  All rights reserved.
 **************************************************************************/

/** Dummy compute program for reflection of the structured buffer types.

     Falcor requires reflection data to be able to create a structured buffer,
     but the programs are not yet ready to be used when we create the buffers.
     Therefore we create this dummy program to make it easier.

     Material type imports are required so that scene type conformances
     (e.g. StandardMaterial : IMaterial) can be resolved when this program
     is compiled with the base ProgramDesc that includes them.
 */
#include "Scene/SceneDefines.slangh"

import RenderPasses.ReSTIRPTPass.PathReservoir;

StructuredBuffer<PathReservoir> outputReservoirs;
StructuredBuffer<PixelReconnectionData> reconnectionDataBuffer;
StructuredBuffer<PathReuseMISWeight> misWeightBuffer;

void main() {}

