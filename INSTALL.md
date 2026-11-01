# Installation

## Start with Codex

Copy this request into Codex:

```text
Use skill-installer to install concept-to-book from
https://github.com/Benz4000/benz-concept-to-book/tree/v1.0.1/skills/concept-to-book
Preserve an existing installation and ask before replacing it.
```

This prepares an installation request. It does not install anything automatically. Codex needs its skill-installer and permitted network access; review the request and any permissions. The source link is pinned to this release.

## Manual installation

1. Download [concept-to-book-v1.0.1.zip](https://github.com/Benz4000/benz-concept-to-book/releases/download/v1.0.1/concept-to-book-v1.0.1.zip) from [release 1.0.1](https://github.com/Benz4000/benz-concept-to-book/releases/tag/v1.0.1).
2. Compare its SHA-256 with the release checksum file: `f5ae1be76c3cd50e50a116e5c40e05f496c1c1d9057df7ebf61b4c5f9dfd66ce`.
3. Extract its single `concept-to-book/` folder into your chosen local skills directory. Preserve an existing installation.
4. Confirm `concept-to-book/SKILL.md` and its relative resources remain together. Select or invoke the skill in your host.

### Windows PowerShell example for Codex

Run in the directory containing the downloaded ZIP:

```powershell
$skillRoot = Join-Path $HOME '.agents/skills'
$skillPath = Join-Path $skillRoot 'concept-to-book'
if (Test-Path -LiteralPath $skillPath) { throw 'Preserve the existing installation before continuing.' }
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
Expand-Archive -LiteralPath './concept-to-book-v1.0.1.zip' -DestinationPath $skillRoot
Get-Item -LiteralPath (Join-Path $skillPath 'SKILL.md')
```

### macOS / Linux example for Codex

```sh
mkdir -p "$HOME/.agents/skills"
if [ -e "$HOME/.agents/skills/concept-to-book" ]; then
  echo 'Preserve the existing installation before continuing.' >&2
  exit 1
fi
unzip './concept-to-book-v1.0.1.zip' -d "$HOME/.agents/skills"
test -f "$HOME/.agents/skills/concept-to-book/SKILL.md"
```

After installation, try:

```text
$concept-to-book
Help me develop this fiction concept into an outline.
Use my existing decisions and tell me which references you consult.
```

The writing guidance does not require a particular vault, publisher or builder. Later file-production helpers require their documented optional runtimes, libraries, permitted fonts and tools. Installing a skill does not install those dependencies or authorize uploads, purchases, reader contact or proof approval. See [platform-specific compatibility notes](COMPATIBILITY.md).

No automatic update or overwrite is configured. Earlier version folders and versioned downloads remain available. No license has been selected for this publication.
