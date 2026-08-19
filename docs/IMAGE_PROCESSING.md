# Image Processing

Pixel Forge builds the main preview in this order:

1. crop the selected source region;
2. apply the selected size mode and resampling method;
3. apply the single option selected in **Process**;
4. optionally quantize the resulting preview through the separate palette workflow.

Choose **Actual** to retain the selected region's native dimensions. **Preserve**
also avoids resizing when W and H already match the selected region. The Process
operations do not require a resize.

## Cluster Cleanup

**Cluster Cleanup** reduces isolated exact-color islands while retaining hard
pixel boundaries. It labels four-way-connected regions of identical RGBA pixels.
Components whose area is at or below **Cleanup threshold** are candidates for
replacement by an adjacent component's existing color.

Merge targets are selected deterministically by shared boundary length, then Lab
color similarity, neighbor area, and row-major component order. The operation
never interpolates pixels, changes dimensions, or introduces an RGBA color that
was not already present in an adjacent component.

Transparency is conservative: fully transparent components are preserved and
cannot absorb opaque artwork. Other components can merge only into neighbors
with the same alpha value. A candidate without an eligible neighbor remains
unchanged.

Cleanup is a single simultaneous pass based on the original component graph.
This avoids order-dependent cascades, but it does not guarantee that every
resulting component is larger than the threshold. Run cleanup again explicitly
if another pass is desired.

Cluster Cleanup runs before explicit preview quantization, like the other Process
options. To clean an already quantized image, apply the palette to the source and
then select Cluster Cleanup.
