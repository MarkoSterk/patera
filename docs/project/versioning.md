# Versioning and releases

## Package versions

Patera and its extension packages follow [semantic versioning](https://semver.org):
`major.minor.patch`.

- **Before 1.0**, a minor release may contain breaking changes. They are listed first in each
  release of the [changelog](changelog.md).
- Each extension package has **its own version**, independent of the core. Every package declares
  the core versions it supports (currently `patera>=0.121`).
- A core 1.0 release does not change every extension's maturity: the AI interface, desktop and
  desktop UI packages stay experimental until their own stability requirements are met.

Pin versions in applications and read the changelog before upgrading a minor version.

## Documentation versions

The documentation is versioned per **minor release** of the core package (`0.123`, `0.124`,
`1.0`, ...). Patch releases update the documentation of their minor version.

| Version | Content |
| --- | --- |
| `latest` (alias, default) | the newest stable release |
| `X.Y` | the documentation as it was released with that version |
| `dev` | the `main` branch, for the next unreleased version |

Use the version selector in the header to switch. Pages of older versions stay available, so the
documentation matches the version you have installed.

How versions are published is described in [Writing the documentation](documentation.md#publishing-versions).
