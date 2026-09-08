---
uid: dc6c96
type: identity
status: approved
content_hash: 27774803de93bdc7
source: "Matrix Cookbook §2.5, eq. 120, p. 13"
unit: "matrix-cookbook:2.5:120"
frequency: rare
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}\otimes\mathbf{X})$

## back
$2\text{Tr}(\mathbf{X})\mathbf{I}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$; $\otimes$ the Kronecker product; $\mathbf{I}$ of the size of $\mathbf{X}$. Denominator layout.

## proof
$\text{Tr}(\mathbf{X} \otimes \mathbf{X}) = \text{Tr}(\mathbf{X})^2$, and $\partial\,\text{Tr}(\mathbf{X})/\partial\mathbf{X} = \mathbf{I}$, so the chain rule gives $2\text{Tr}(\mathbf{X})\mathbf{I}$.
