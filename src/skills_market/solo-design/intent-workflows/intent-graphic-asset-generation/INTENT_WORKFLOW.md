---
lane: graphic_bitmap_first
surface: graphic
---

# Intent Workflow: Graphic Asset Generation

Use this workflow for bitmap-first static visual deliverables and appended generated image assets.

## Context Requirements

- `shared-runtime/runtime-boundaries/lane-runtime-contracts.md`
- `shared-runtime/design-artifact-formats/graphic-asset-design-file-format.md`
- `shared-runtime/deterministic-tooling/validate-graphic-asset-design.mjs`
- `delivery-quality/delivery-evidence-contract.md`

## Runtime Files

- Workflow entry: `start-graphic-asset-project.md`
- Append workflow: `append-graphic-assets.md`
- Dispatch contract: `graphic-asset-dispatch-contract.md`
- Summary fields: `orchestration-summary-fields.md`
- Planning: `graphic-asset-planning.md`
- Text gate: `graphic-text-controllability-gate.md`

## Hard Rules

- Do not load page runtime guides for bitmap-first output.
- Do not load `visual-experience/`.
- Route text-critical, editable, or long-copy graphics to `intent-project-complex-build` with `graphic_layout_static`.

## Workflow

1. Classify bitmap-first versus append mode.
2. Apply `graphic-text-controllability-gate.md`, record `textCriticality`, `copyDensity`, `graphicStrategyGate`, `bitmapFirstAllowed`, and `layoutStaticRequired`; redirect text-critical layout work to `graphic_layout_static`.
3. Plan assets with `graphic-asset-planning.md`.
4. Generate or collect assets, write them under `assets/`, and register every kept image as a `.design` image node.

## Dispatch

- Page Sub-Agent dispatch is not used for pure bitmap-first or pure append mode.
- Asset generation follows `graphic-asset-dispatch-contract.md`.

## Summary Writes

- Write `project.resolvedLane` after the graphic strategy gate.
- Record generated/appended asset inventory and image-node registration proof in `orchestration-summary-fields.md`.

## Delivery Quality Gate

- Run `shared-runtime/deterministic-tooling/validate-graphic-asset-design.mjs` for image-only projects.
- For mixed existing projects, the Main Agent validates the normal `.design` asset invariant through the owning mutation workflow.

## Completion Evidence

- Completion must include asset count, `.design` image node ids, validation result, and any blocked reason.
