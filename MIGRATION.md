# Repository migration

This repository was split directly from `skedup/kindred-private` without rewriting or copying its
Git history.

- Source repository: `https://github.com/skedup/kindred-private`
- Source commit: `7d9875b4c91c9acd0f643b9e35e32489fad4769b`
- Public VisualState contract source: `https://github.com/skedup/kindred`
- Public VisualState contract commit: `b7b025b15deba366b10c141a089052ae330180be`
- Migration policy: `docs/plans/2026-08-23-desktop-repository-separation-plan.md` in the source repository

Only Git-tracked desktop paths were copied. Local experimental directories such as `frame2c/`,
`frame2d/`, and `monica_img/`, as well as build caches and generated distributions, were excluded.

