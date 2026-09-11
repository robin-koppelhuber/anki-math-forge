---
uid: 8255c6
type: identity
status: approved
content_hash: d6fd294c06003756
source: "Matrix Cookbook §2.8, eq. 143, p. 16"
unit: "matrix-cookbook:2.8:143, matrix-cookbook:2.8:p16y225, matrix-cookbook:2.8:p16y250, matrix-cookbook:2.8:p16y267, matrix-cookbook:2.8:p16y320"
frequency: rare
derivation: short
tags: [derivatives, trace, toeplitz]
verify: false
---

## front
$\frac{\partial \text{Tr}(\mathbf{A}\mathbf{T})}{\partial \mathbf{T}}$ for Toeplitz $\mathbf{T}$

## back
$\boldsymbol{\alpha}(\mathbf{A})$, the Toeplitz matrix with $[\boldsymbol{\alpha}(\mathbf{A})]_{ij} = \sum_k A_{k,\,k+i-j}$

## conditions
$\mathbf{T} \in \mathbb{R}^{n \times n}$; $T_{ij} = t_{i-j}$, varied over the $t_d$, one per diagonal. Denominator layout.

## prose
One parameter of $\mathbf{T}$ sets a whole diagonal, so each entry of the derivative sums a whole diagonal of $\mathbf{A}$, and $\boldsymbol{\alpha}(\mathbf{A})$ comes out Toeplitz.

## uses
The weight gradient of a 1-D convolution, whose operator matrix is Toeplitz in the filter taps.

## proof
A Toeplitz $\mathbf{T}$ has one independent parameter $t_d$ per diagonal, $T_{ij} = t_{i-j}$, so $\text{Tr}(\mathbf{A}\mathbf{T}) = \sum_d t_d \sum_k A_{k,\,k+d}$ and $\partial/\partial t_d$ is the sum of the $d$-th diagonal of $\mathbf{A}$.
