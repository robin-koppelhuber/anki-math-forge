---
uid: a35122
type: identity
status: approved
content_hash: 1e8d3a0e05ac8ac5
source: "Matrix Cookbook §2.4, eq. 90, p. 11"
unit: "matrix-cookbook:2.4:90"
frequency: common
derivation: short
tags: [derivatives, matrix-powers]
verify: false
---

## front
$\frac{\partial (\mathbf{X}^n)_{kl}}{\partial X_{ij}}$

## back
$\sum_{r=0}^{n-1}\left(\mathbf{X}^r\mathbf{J}^{ij}\mathbf{X}^{n-1-r}\right)_{kl}$

## conditions
$\mathbf{X} \in \mathbb{R}^{m \times m}$; $n \in \mathbb{Z}_{>0}$.

## proof
The product rule over the $n$ copies of $\mathbf{X}$: summand $r$
differentiates the factor at position $r+1$, replacing it by $\mathbf{J}^{ij}$
and leaving $\mathbf{X}^r$ to its left and $\mathbf{X}^{n-1-r}$ to its right.

## prose
Here $\mathbf{J}^{ij}$ has a single $1$ at $(i,j)$ and zeros everywhere else (the single-entry matrix).
