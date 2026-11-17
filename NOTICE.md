# Third-party notices

This project wraps, but does not modify, the following MIT-licensed projects:

- **ZV-E10-5GHz-WiFi-Unlock** — https://github.com/dino2048/ZV-E10-5GHz-WiFi-Unlock
  Copyright (c) 2026 dino2048. MIT License.
  Pinned main repository commit used during development: `9def1681ee20a88f26daaf7ae43f4dbc51b43b2d`.

- **zv-e10-toolkit** — https://github.com/dino2048/zv-e10-toolkit
  Copyright (c) 2026 dino2048. MIT License.
  Pinned commit: `373bd482f9ef4e54ecaf5faf00e0afcbb4f041de`.

- **Sony-PMCA-RE** — https://github.com/ma1co/Sony-PMCA-RE
  MIT License. Pinned revision used by the toolkit: `a82f5baaa8e9c3d9f28f94699e860fb2e48cc8e0`.

## Not included

This repository does **not** contain, and must not be used to distribute:

- Sony's `ud_wbi_drop.elf` or any other Sony binary
- Sony camera firmware or update packages
- BootROM dumps
- Device backups or `private/` session data
- Service keys, certificates, or device identifiers

Users must obtain any Sony utility from their own official update package. The
installer only verifies size and SHA-256; it never bundles the file.
