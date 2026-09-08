---
uid: c404e3
type: identity
status: approved
content_hash: c94b430fb8bf1657
source: "Matrix Cookbook §2.6, eq. 131, p. 14"
unit: "matrix-cookbook:2.6:131"
frequency: core
derivation: short
tags: [derivatives, norms, two-norm]
verify: false
---

## front
$\frac{\partial \|\mathbf{x}\|_2^2}{\partial \mathbf{x}}$

## back
$2\mathbf{x}$

## conditions
Denominator layout.

## proof
$\|\mathbf{x}\|_2^2 = \sum_i x_i^2$, so $\partial\|\mathbf{x}\|_2^2/\partial x_i = 2x_i$.

## notes
Overlaps eq. 81 (§2.4), $\partial\mathbf{x}^\top\mathbf{B}\mathbf{x}/\partial\mathbf{x} = (\mathbf{B}+\mathbf{B}^\top)\mathbf{x}$, at $\mathbf{B} = \mathbf{I}$. Kept because the squared-norm front is the one that comes up.
