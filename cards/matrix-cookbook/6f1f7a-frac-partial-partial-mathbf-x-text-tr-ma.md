---
uid: 6f1f7a
type: identity
status: approved
content_hash: 4c2ece723d4bf680
source: "Matrix Cookbook §2.5, eq. 115, p. 13"
unit: "matrix-cookbook:2.5:115"
frequency: core
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}^T\mathbf{X})$

## back
$2\mathbf{X}$

## conditions
Denominator layout.

## prose
$\text{Tr}(\mathbf{X}^T\mathbf{X}) = \text{Tr}(\mathbf{X}\mathbf{X}^T) = \|\mathbf{X}\|_F^2$, so this is the gradient of the squared Frobenius norm, the matrix analogue of $(x^2)' = 2x$.
