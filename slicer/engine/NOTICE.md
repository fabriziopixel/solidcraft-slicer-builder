# Third-party engine and release restrictions

The lab uses Bambu Studio v02.08.02.61, associated source commit:
https://github.com/bambulab/BambuStudio/tree/926a7192574bcb9b3a732e1ec59a46d79cb45466

Bambu Studio declares GNU Affero General Public License v3; the unmodified upstream license text is supplied as `LICENSE.BambuStudio.txt`. Preserve upstream copyright/license notices. The source tree's dependencies and bundled assets may have their own terms; the OS package inventory is not a complete license clearance or SPDX SBOM of the AppImage.

No proprietary Bambu networking plugin is included, downloaded, reverse-engineered or authorized by this integration. Printing is not sent to any device or cloud. No protections or proprietary protocols have been bypassed.

No Bambu binary code is patched in this milestone. B2 adds two uncompiled metadata source-patch candidates under `patches/` and an optional uncompiled X11/GLX variant under `experiments/`, derived from the pinned AGPL-3.0 upstream source; these are supplied under the same upstream license (see `LICENSE.BambuStudio.txt`). They have not been incorporated into the lab image. Preserve the upstream notices and supply the complete corresponding source/build material before any applicable distribution/deployment. Packaging copies the exact upstream A1 model metadata into the directory the CLI expects; wrapper/build/lab code is separately tracked in this repository. If a modified engine, derivative harness or combined service is distributed/deployed, provide the exact Corresponding Source, applicable build material and notices as required by the licenses. A separate CLI process is not an automatic copyleft exemption for SolidCraft. Ownership/licensing of SolidCraft and the combined-work scope must be resolved before public release, with legal review where needed.

The current artifact is private lab/staging work, not a declaration of legal approval for a closed-source hosted service or a public software release. Never include credentials, personal project files or backup keys in a source offer.
