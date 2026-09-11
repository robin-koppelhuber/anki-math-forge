---
uid: b92035
type: identity
status: approved
content_hash: 42e810c30df9267a
source: "Matrix Cookbook §2.3, eq. 65, p. 10"
unit: "matrix-cookbook:2.3:65"
frequency: common
derivation: short
requires: [827eae, 7b7520]
tags: [derivatives, eigenvalues, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}} \sum_i \lambda_i$ where $\lambda_i = \text{eig}(\mathbf{X})$

## back
$\mathbf{I}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$; $\lambda_i$ counted over $\mathbb{C}$
with algebraic multiplicity.

## proof
$\sum_i \lambda_i = \operatorname{Tr}(\mathbf{X})$, and $\partial \operatorname{Tr}(\mathbf{X})/\partial X_{ij}$ is $1$ when $i = j$ and $0$ otherwise, which is $\mathbf{I}$.

## notes
This composes two facts the deck already holds separately: $\sum_i\lambda_i = \operatorname{Tr}(\mathbf{X})$, and $\partial\operatorname{Tr}(\mathbf{X})/\partial\mathbf{X} = \mathbf{I}$ (eq. 99, §2.5). Kept because the eigenvalue-sum front is the one a reader meets; reject if that overlap is not wanted.
