# CCSDESIGN Rebuild — iPhone companion (RTX 3080 host)

## Architecture
The Windows PC runs the FastAPI application and performs GPU reconstruction. Safari on the iPhone opens the same React frontend through a private encrypted Tailscale connection. Projects and files stay on the Windows PC; no paid inference API is required.

## Current implementation status
- The existing React interface is now responsive on iPhone-sized screens.
- The current launcher binds to 127.0.0.1:8000, which is appropriate for a local reverse proxy.
- The current reconstruction engine is Meshroom/AliceVision, which requires overlapping views. Changing the photo minimum in the UI does NOT enable genuine one-photo 3D generation.
- A local, RTX 3080 10GB-compatible single-image inference pipeline still needs to be integrated and validated.
- Remote access has NOT yet been end-to-end tested.

## Private access plan
1. Install Tailscale on the Windows PC and iPhone; sign in to the same tailnet.
2. Start CCSDESIGN Rebuild on the PC; verify http://127.0.0.1:8000 works.
3. On the Windows PC, use Tailscale Serve to proxy the local application to the tailnet over HTTPS. Follow the current official Tailscale Serve instructions for your installed version; do not use Tailscale Funnel (public internet exposure).
4. Open the HTTPS tailnet URL in Safari on the iPhone. Add to Home Screen if desired.
5. Keep the PC awake while processing. Use tailnet device restrictions and account MFA. Do not forward port 8000 on the router.

## Security requirements before release
- Add per-user authentication and project authorization before allowing access from any public network.
- Protect file uploads, project deletion, exports and settings; enforce upload limits and validate file contents.
- Keep Tailscale Serve restricted to your tailnet. Do not expose the unauthenticated FastAPI service through Funnel or a public tunnel.
- Test iPhone Safari uploads, 3D viewer touch gestures, job polling and file downloads over HTTPS.

## Reconstruction milestones
1. Make one image upload succeed independently of reconstruction readiness.
2. Add local single-image AI reconstruction with a supported model and licence, optimized for 10GB VRAM.
3. Preserve the multi-photo Meshroom route for suitable overlapping image sets.
4. Add GPU memory/error reporting, queueing, progress and cancellation.
5. Test on Windows and iPhone with real input images; package a Windows installer and publish the private mobile access instructions.
