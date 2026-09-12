---
uid: 95bdb4
type: identity
status: approved
content_hash: f03c27a38cd2ab9c
source: "Matrix Cookbook §2.8, eq. 139, p. 15"
unit: "matrix-cookbook:2.8:139"
gist: "the derivative of a trace, X symmetric"
frequency: common
derivation: short
tags: [derivatives, trace, symmetric]
verify: false
---

## front
$\frac{\partial \text{Tr}(\mathbf{A}\mathbf{X})}{\partial \mathbf{X}}$ for symmetric $\mathbf{X}$

## back
$\mathbf{A} + \mathbf{A}^T - (\mathbf{A} \circ \mathbf{I})$

## conditions
$\mathbf{X} = \mathbf{X}^T$, varied over $X_{ij}$ with $i \le j$ only, the rest following by symmetry. Denominator layout.

## prose
Here $\circ$ multiplies entry by entry (the Hadamard product). Free entries give $\mathbf{A}^T$; constraining $\mathbf{X}$ to be symmetric adds the mirror image and subtracts $\mathbf{A} \circ \mathbf{I}$, the diagonal that would otherwise be counted twice.

## proof
Varying all $n^2$ entries of $\mathbf{X}$ independently gives $\mathbf{A}^T$; the symmetric rule $\mathbf{G} + \mathbf{G}^T - \text{diag}(\mathbf{G})$ with $\mathbf{G} = \mathbf{A}^T$ gives $\mathbf{A}^T + \mathbf{A} - (\mathbf{A} \circ \mathbf{I})$.
