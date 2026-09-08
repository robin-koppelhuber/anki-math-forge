---
uid: 2da328
type: identity
status: approved
content_hash: 4440258084d1350d
source: "Matrix Cookbook §2, eq. 40, p. 8"
unit: "matrix-cookbook:2:40"
frequency: core
derivation: short
tags: [derivatives, differential, inverse]
verify: false
---

## front
$\partial(\mathbf{X}^{-1})$

## back
$-\mathbf{X}^{-1}(\partial\mathbf{X})\mathbf{X}^{-1}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible.

## proof
Differentiate $\mathbf{X}\mathbf{X}^{-1} = \mathbf{I}$ with the product rule:
$(\partial\mathbf{X})\mathbf{X}^{-1} + \mathbf{X}\,\partial(\mathbf{X}^{-1}) = \mathbf{0}$.
Left-multiplying by $\mathbf{X}^{-1}$ gives the result.

## prose
The matrix analogue of $d(1/x) = -dx/x^2$, with the two copies of
$\mathbf{X}^{-1}$ on opposite sides of $\partial\mathbf{X}$.
