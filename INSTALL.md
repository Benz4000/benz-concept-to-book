# Installation

## Start with Codex

Copy this request into Codex:

```text
Use skill-installer to install concept-to-book-v6 from
https://github.com/Benz4000/benz-concept-to-book/tree/v6.0.0/skills/concept-to-book-v6
Preserve an existing installation and ask before replacing it.
```

This prepares an installation request. It does not install anything automatically. Codex needs its skill-installer and permitted network access; review the request and any permissions. The source link is pinned to this release.

## Manual installation

1. Download [concept-to-book-v6.0.0.zip](https://github.com/Benz4000/benz-concept-to-book/releases/download/v6.0.0/concept-to-book-v6.0.0.zip) from [release 6.0.0](https://github.com/Benz4000/benz-concept-to-book/releases/tag/v6.0.0).
2. Compare its SHA-256 with the release checksum file: `a8b9abca3cff048aec190301ac56b228b9e8a00127a7d581df71e5c55da6b35e`.
3. Extract its single `concept-to-book-v6/` folder into your chosen local skills directory. Preserve an existing installation.
4. Confirm `concept-to-book-v6/SKILL.md` and its relative resources remain together. Select or invoke the skill in your host.

### Windows PowerShell example for Codex

Run in the directory containing the downloaded ZIP:

```powershell
$skillRoot = Join-Path $HOME '.agents/skills'
$skillPath = Join-Path $skillRoot 'concept-to-book-v6'
if (Test-Path -LiteralPath $skillPath) { throw 'Preserve the existing installation before continuing.' }
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
Expand-Archive -LiteralPath './concept-to-book-v6.0.0.zip' -DestinationPath $skillRoot
Get-Item -LiteralPath (Join-Path $skillPath 'SKILL.md')
```

### macOS / Linux example for Codex

```sh
mkdir -p "$HOME/.agents/skills"
if [ -e "$HOME/.agents/skills/concept-to-book-v6" ]; then
  echo 'Preserve the existing installation before continuing.' >&2
  exit 1
fi
unzip './concept-to-book-v6.0.0.zip' -d "$HOME/.agents/skills"
test -f "$HOME/.agents/skills/concept-to-book-v6/SKILL.md"
```

After installation, try:

```text
$concept-to-book-v6
Help me develop this fiction concept into an outline.
Use my existing decisions and tell me which references you consult.
```

The writing guidance does not require a particular vault, publisher or builder. Later file-production helpers require their documented optional runtimes, libraries, permitted fonts and tools. Installing a skill does not install those dependencies or authorize uploads, purchases, reader contact or proof approval. See [platform-specific compatibility notes](COMPATIBILITY.md).

No automatic update or overwrite is configured. Earlier version folders and versioned downloads remain available. No license has been selected for this publication.
