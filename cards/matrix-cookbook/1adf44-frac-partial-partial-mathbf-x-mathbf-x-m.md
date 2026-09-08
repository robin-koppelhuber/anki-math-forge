---
uid: 1adf44
type: identity
status: approved
content_hash: b66d1e4d1cfce73a
source: "Matrix Cookbook §2.6, eq. 129, p. 14"
unit: "matrix-cookbook:2.6:129"
frequency: core
derivation: short
tags: [derivatives, norms, two-norm]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{x}}\|\mathbf{x}-\mathbf{a}\|_2$

## back
$\dfrac{\mathbf{x}-\mathbf{a}}{\|\mathbf{x}-\mathbf{a}\|_2}$

## conditions
$\mathbf{x} \neq \mathbf{a}$. Denominator layout.

## prose
The unit vector pointing from $\mathbf{a}$ to $\mathbf{x}$: moving away from $\mathbf{a}$ at unit speed increases the distance at unit rate.
