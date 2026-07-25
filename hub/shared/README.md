# Hub shared-package links

`edge-runtime` points to the canonical package at `../../shared/edge-runtime`. This keeps the Hub lock file self-contained in a repository checkout.

`scripts/install_service.sh` excludes the link while copying a Hub deployment and materializes its verified target as a real directory before running the frozen production dependency install. Do not replace the link with a copied source tree in the repository.
