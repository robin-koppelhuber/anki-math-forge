---
uid: e6da40
type: identity
status: approved
content_hash: 337be91943d7105e
source: "Matrix Cookbook §2.8, eq. 141, p. 15"
unit: "matrix-cookbook:2.8:141"
frequency: core
derivation: short
tags: [derivatives, determinant, symmetric]
verify: false
---

## front
$\frac{\partial \ln\det(\mathbf{X})}{\partial \mathbf{X}}$ for symmetric $\mathbf{X}$

## back
$2\mathbf{X}^{-1} - (\mathbf{X}^{-1} \circ \mathbf{I})$

## conditions
$\mathbf{X} = \mathbf{X}^T$, varied over $X_{ij}$ with $i \le j$ only, the rest following by symmetry; $\det(\mathbf{X}) > 0$. Denominator layout.

## proof
Varying all $n^2$ entries independently gives $\mathbf{X}^{-T}$; the symmetric rule $\mathbf{G} + \mathbf{G}^T - \text{diag}(\mathbf{G})$ with $\mathbf{X}^{-1}$ symmetric gives $2\mathbf{X}^{-1} - (\mathbf{X}^{-1} \circ \mathbf{I})$.

## prose
Here $\circ$ multiplies entry by entry (the Hadamard product). The factor $2$ is the off-diagonal pairing of a symmetric $\mathbf{X}$, and the Hadamard term takes that doubling back off the diagonal.
