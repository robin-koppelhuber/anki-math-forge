---
uid: 18ee56
type: identity
status: approved
content_hash: fefbc58cec88dda9
source: "Matrix Cookbook §2.5, eq. 105, p. 12"
unit: "matrix-cookbook:2.5:105"
gist: the derivative of the trace of a Kronecker product
frequency: rare
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{A}\otimes\mathbf{X})$

## back
$\text{Tr}(\mathbf{A})\mathbf{I}$

## conditions
$\mathbf{A} \in \mathbb{R}^{m \times m}$; $\mathbf{X} \in \mathbb{R}^{n \times n}$; $\otimes$ the Kronecker product. Denominator layout.

## proof
$\text{Tr}(\mathbf{A} \otimes \mathbf{X}) = \text{Tr}(\mathbf{A})\text{Tr}(\mathbf{X})$, so this is the constant $\text{Tr}(\mathbf{A})$ times $\partial\,\text{Tr}(\mathbf{X})/\partial\mathbf{X} = \mathbf{I}$.
