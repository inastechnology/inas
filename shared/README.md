# Shared platform components

This directory owns reusable boundaries shared by Local Hub and Edge Gateway appliances.

- `contracts/sync/v1/` is the language-neutral parent/child HTTPS contract and its conformance vectors.
- `edge-runtime/` is the standard-library-only Python runtime package shared by Local Hub and Edge Gateway.

`shared/edge-runtime/` is the canonical source. The Local Hub exposes it through `hub/shared/edge-runtime` for locked dependency resolution. Production Hub deployment materializes that package inside the Hub bundle; generated copies must not become a second source of truth.
