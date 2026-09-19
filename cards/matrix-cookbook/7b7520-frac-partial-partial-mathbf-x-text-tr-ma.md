---
uid: 7b7520
type: identity
status: approved
content_hash: a3e0843eec07a5d6
source: "Matrix Cookbook §2.5, eq. 99, p. 12"
unit: "matrix-cookbook:2.5:99"
gist: the derivative of the trace
frequency: core
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X})$

## back
$\mathbf{I}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$. Denominator layout.

## prose
Every diagonal entry of $\mathbf{X}$ enters $\text{Tr}(\mathbf{X})$ exactly once and no off-diagonal entry enters at all.
