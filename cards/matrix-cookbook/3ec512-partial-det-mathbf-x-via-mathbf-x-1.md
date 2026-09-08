---
uid: 3ec512
type: identity
status: approved
content_hash: 5f3524cbd4b44b36
source: "Matrix Cookbook §2, eq. 42, p. 8"
unit: "matrix-cookbook:2:42"
frequency: core
derivation: short
tags: [derivatives, differential, determinant]
verify: false
---

## front
$\partial(\det(\mathbf{X}))$ via $\mathbf{X}^{-1}$

## back
$\det(\mathbf{X})\text{Tr}(\mathbf{X}^{-1}\partial\mathbf{X})$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible.

## prose
$\text{adj}(\mathbf{X}) = \det(\mathbf{X})\mathbf{X}^{-1}$ turns the adjugate
form $\text{Tr}(\text{adj}(\mathbf{X})\,\partial\mathbf{X})$ into this one.
