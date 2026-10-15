# Verifying releases

Every Varken release is built and published by the [`release.yml`](../.github/workflows/release.yml)
workflow when a version tag is pushed. You can check that what you run came from that workflow, unchanged:

- the **image** on GHCR is signed with [cosign](https://docs.sigstore.dev/) "keylessly": the signature is
  tied to the workflow's GitHub identity through [Sigstore](https://www.sigstore.dev/), so there is no
  long-lived signing key to steal, and every signature is recorded in the public Rekor transparency log;
- the image carries an **SBOM** (software bill of materials) and **SLSA provenance** (how and from which
  commit it was built) as attestations;
- each GitHub Release has a source archive (`varken-<version>.tar.gz`, with the license), `image.txt` (the
  image digest) and `SHA256SUMS`, which is signed the same way (`SHA256SUMS.sigstore.json`), plus **SLSA
  build provenance** for those files (`varken-<version>.provenance.sigstore.json`, also stored by GitHub, and
  the same provenance as in-toto JSON Lines in `varken-<version>.intoto.jsonl`);
- the **version tag** in git is signed with the maintainer's SSH key.

This applies to releases from **2.0.0 onward**, the first release from this repository; none has been
published yet. Upstream Boerderij/Varken releases and the `boerderij/varken` images were not signed this
way and can't be verified with these commands. You need
[cosign](https://docs.sigstore.dev/cosign/system_config/installation/) 3.0 or later (with cosign 2.6, add
`--new-bundle-format` to `cosign verify`). The examples use version 2.0.0; substitute the one you run.

## The image

```sh
cosign verify ghcr.io/honeybeartech/varken:2.0.0 \
  --certificate-identity https://github.com/HoneyBearTech/Varken/.github/workflows/release.yml@refs/tags/v2.0.0 \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

The certificate identity names the workflow file and the tag it ran on (`refs/tags/vX.Y.Z`), so a signature
made for another version, another workflow or another repository fails. cosign prints the verified
signatures, including the commit they were built from. A tag such as `2.0.0` can be moved, a digest can't:
for the strongest guarantee, pin the digest from the release's `image.txt` (after verifying it, below), for
example `image: ghcr.io/honeybeartech/varken@sha256:…` in your compose file.

With the [GitHub CLI](https://cli.github.com/) you can also check the image's provenance against this
repository:

```sh
gh attestation verify oci://ghcr.io/honeybeartech/varken:2.0.0 --repo HoneyBearTech/Varken
```

To see the SBOM and the provenance:

```sh
docker buildx imagetools inspect ghcr.io/honeybeartech/varken:2.0.0 --format '{{ json .SBOM }}'
docker buildx imagetools inspect ghcr.io/honeybeartech/varken:2.0.0 --format '{{ json .Provenance }}'
```

## The release files

Download `SHA256SUMS`, `SHA256SUMS.sigstore.json`, `image.txt` and the source archive from the
[release page](https://github.com/HoneyBearTech/Varken/releases), then:

```sh
cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json \
  --certificate-identity https://github.com/HoneyBearTech/Varken/.github/workflows/release.yml@refs/tags/v2.0.0 \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum -c SHA256SUMS
```

The first command proves `SHA256SUMS` came from the release workflow for that tag; the second, that the
archive and `image.txt` match it.

## Build provenance

Check that a downloaded release file was built by this repository's release workflow:

```sh
gh attestation verify varken-2.0.0.tar.gz --repo HoneyBearTech/Varken \
  --signer-workflow HoneyBearTech/Varken/.github/workflows/release.yml
```

To verify offline, add `--bundle varken-2.0.0.provenance.sigstore.json`. Every file listed in `SHA256SUMS`
is covered.

## The git tag

The maintainer signs version tags with an SSH key whose public half is in
[`.github/allowed_signers`](../.github/allowed_signers):

```sh
git clone https://github.com/HoneyBearTech/Varken.git && cd Varken
git -c gpg.ssh.allowedSignersFile=.github/allowed_signers verify-tag v2.0.0
```

It should print `Good "git" signature for 31805425+HoneyBearTech@users.noreply.github.com`. Check
`.github/allowed_signers` against the key published at <https://github.com/HoneyBearTech.keys> rather than
trusting the copy in the same checkout alone.

## If a check fails

Don't run that image or file. Pull or download it again; if the check still fails, report it privately as a
security issue ([SECURITY.md](../SECURITY.md)).
