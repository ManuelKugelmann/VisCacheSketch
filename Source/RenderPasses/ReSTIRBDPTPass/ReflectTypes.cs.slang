/** Dummy compute program for reflection of the structured buffer types.

     Falcor requires reflection data to be able to create a structured buffer,
     but the programs are not yet ready to be used when we create the buffers.
     Therefore we create this dummy program to make it easier.
 */

#define SWAP_RESERVOIRS 0
import PathGenerator;

void main() {}
