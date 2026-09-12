---
uid: a35122
type: identity
status: approved
content_hash: fcb95f27d17325ce
source: "Matrix Cookbook §2.4, eq. 90, p. 11"
unit: "matrix-cookbook:2.4:90"
gist: the derivative of a matrix power by one entry
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

## prose
Here $\mathbf{J}^{ij}$ has a single $1$ at $(i,j)$ and zeros everywhere else (the single-entry matrix).

## proof
The product rule over the $n$ copies of $\mathbf{X}$: summand $r$
differentiates the factor at position $r+1$, replacing it by $\mathbf{J}^{ij}$
and leaving $\mathbf{X}^r$ to its left and $\mathbf{X}^{n-1-r}$ to its right.
