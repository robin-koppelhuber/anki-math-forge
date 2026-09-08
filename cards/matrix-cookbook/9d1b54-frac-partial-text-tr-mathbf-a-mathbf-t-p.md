---
uid: 9d1b54
type: identity
status: approved
content_hash: 3d8c4642d18125c1
source: "Matrix Cookbook §2.8, eq. 144, p. 16"
unit: "matrix-cookbook:2.8:144"
frequency: rare
derivation: short
tags: [derivatives, trace, toeplitz, symmetric]
verify: false
---

## front
$\frac{\partial \text{Tr}(\mathbf{A}\mathbf{T})}{\partial \mathbf{T}}$ for symmetric Toeplitz $\mathbf{T}$

## back
$\boldsymbol{\alpha}(\mathbf{A}) + \boldsymbol{\alpha}(\mathbf{A})^T - \boldsymbol{\alpha}(\mathbf{A}) \circ \mathbf{I}$

## conditions
$T_{ij} = t_{i-j}$ with $t_{-d} = t_d$, varied over the $t_d$ with $d \ge 0$; $[\boldsymbol{\alpha}(\mathbf{A})]_{ij} = \sum_k A_{k,\,k+i-j}$. Denominator layout.

## uses
Fitting a Gaussian process whose covariance depends only on the gap between points (stationary).

## prose
Here $\circ$ Hadamard product. Symmetry ties $t_d$ to $t_{-d}$, which is the same pairing that turns $\mathbf{G}$ into $\mathbf{G} + \mathbf{G}^T - \text{diag}(\mathbf{G})$ for a symmetric matrix.
