# Code signing policy

## Current status

PingVault is an open-source Windows application distributed through GitHub Releases.

Free code signing provided by SignPath.io, certificate by SignPath Foundation.

Until the SignPath Foundation application is approved and the signing workflow is enabled, released Windows installers may remain unsigned. The release page will identify the signing status of each artifact.

## Build and signing provenance

Signed artifacts must be produced from this public repository by GitHub Actions. The signing workflow must run only for reviewed release commits or release tags and must publish the signed artifact to the corresponding GitHub Release.

The project will not commit private signing keys, certificates, passwords, or access tokens to this repository.

## Team roles

- **Committer / reviewer:** `yogaliu0818`
- **Approver:** `yogaliu0818`

The approver is responsible for confirming that a release was built from the intended source revision and that the artifact is ready for publication.

## What is signed

The Windows installer and the main PingVault executable are the intended signed artifacts. Third-party runtime libraries may be included by the packaging process but are not signed with the PingVault signing identity.

## Privacy

PingVault does not transfer information to other networked systems unless specifically requested by the user or the person installing or operating it. GitHub Actions and SignPath receive build artifacts and metadata required to build and sign releases.

## Verification

Users can inspect the Authenticode signature in Windows file properties or with:

```powershell
Get-AuthenticodeSignature .\PingVault-Setup.exe
```

Release SHA-256 values are also published for integrity verification.
