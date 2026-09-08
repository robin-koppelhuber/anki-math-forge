---
uid: 2720f4
type: identity
status: approved
content_hash: b7a6e2dc6ce402c7
source: "Matrix Cookbook §2.5, eq. 106, p. 13"
unit: "matrix-cookbook:2.5:106"
frequency: core
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}^2)$

## back
$2\mathbf{X}^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$. Denominator layout.

## prose
$\text{Tr}(\mathbf{X}^2) = \sum_{ij} X_{ij} X_{ji}$ pairs each entry with its mirror, which is where the transpose comes from; $\text{Tr}(\mathbf{X}^T\mathbf{X})$ pairs each entry with itself and gives $2\mathbf{X}$.
