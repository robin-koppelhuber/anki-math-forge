---
uid: 006b28
type: identity
status: approved
content_hash: 261cde27ced4f657
source: "Matrix Cookbook §2.3, eq. 66, p. 10"
unit: "matrix-cookbook:2.3:66"
frequency: common
derivation: short
requires: [af5ca1, ae6e48]
tags: [derivatives, eigenvalues, determinant]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}} \prod_i \lambda_i$ where $\lambda_i = \text{eig}(\mathbf{X})$

## back
$\det(\mathbf{X})\,\mathbf{X}^{-\top}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible; $\lambda_i$ the eigenvalues of $\mathbf{X}$, counted over $\mathbb{C}$ with algebraic multiplicity. Denominator layout.

## proof
$\prod_i \lambda_i = \det(\mathbf{X})$, and Jacobi's formula $d\det(\mathbf{X}) = \det(\mathbf{X})\operatorname{Tr}(\mathbf{X}^{-1}d\mathbf{X})$
read as $\operatorname{Tr}(\mathbf{G}^\top d\mathbf{X})$ gives $\mathbf{G} = \det(\mathbf{X})\mathbf{X}^{-\top}$.

## notes
This composes two facts the deck already holds separately: $\prod_i\lambda_i = \det(\mathbf{X})$ (card af5ca1), and $\partial\det(\mathbf{X})/\partial\mathbf{X}$ (eq. 49, §2.1). Kept for the same reason as eq. 65; reject both together if the overlap is not wanted.
