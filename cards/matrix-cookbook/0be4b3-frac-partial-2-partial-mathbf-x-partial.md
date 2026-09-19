---
uid: 0be4b3
type: identity
status: approved
content_hash: 4187ec09ca76b6b1
source: "Matrix Cookbook §2.4, eq. 96 and 98, p. 12"
unit: "matrix-cookbook:2.4:96, matrix-cookbook:2.4:98"
gist: the Hessian of a quadratic plus a linear form
frequency: core
derivation: short
tags: [derivatives, hessian]
verify: false
---

## front
$\frac{\partial^2}{\partial \mathbf{x}\partial \mathbf{x}^T}\left(\mathbf{x}^T\mathbf{A}\mathbf{x}+\mathbf{b}^T\mathbf{x}\right)$

## back
$\mathbf{A}+\mathbf{A}^T$

## prose
The Hessian is $2\mathbf{A}$ only when $\mathbf{A} = \mathbf{A}^T$, and $\mathbf{b}$ drops out because a linear term has zero second derivative.

## proof
The gradient is $(\mathbf{A}+\mathbf{A}^T)\mathbf{x} + \mathbf{b}$: the quadratic term gives $(\mathbf{A}+\mathbf{A}^T)\mathbf{x}$ and the linear term gives $\mathbf{b}$. Differentiating that once more in $\mathbf{x}^T$ leaves the constant matrix $\mathbf{A}+\mathbf{A}^T$; $\mathbf{b}$ does not depend on $\mathbf{x}$, so it drops.

## notes
