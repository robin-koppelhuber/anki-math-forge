---
uid: df0689
type: identity
status: approved
content_hash: 04ac3360d624cf3a
source: "Matrix Cookbook §2.5, p. 12"
unit: "matrix-cookbook:2.5:p12y482"
gist: the derivative of the trace of a matrix function
frequency: common
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(F(\mathbf{X}))$

## back
$f(\mathbf{X})^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$; $F$ differentiable in each entry of $\mathbf{X}$, $f$ its scalar derivative. Denominator layout.

## prose
Inside a trace the scalar derivative carries over unchanged up to a transpose: $F=\sin$ gives $\cos(\mathbf{X})^T$, $F(x)=x^k$ gives $k(\mathbf{X}^{k-1})^T$.
