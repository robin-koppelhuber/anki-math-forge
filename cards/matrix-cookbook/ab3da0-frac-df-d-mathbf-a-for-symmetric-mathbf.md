---
uid: ab3da0
type: identity
status: approved
content_hash: d907b48e148ccfa1
source: "Matrix Cookbook §2.8, eq. 138, p. 15"
unit: "matrix-cookbook:2.8:138"
gist: correcting a gradient for a symmetric matrix
frequency: common
derivation: short
tags: [derivatives, symmetric]
verify: false
---

## front
$\frac{df}{d\mathbf{A}}$ for symmetric $\mathbf{A}$, given the unconstrained $\left[\frac{\partial f}{\partial \mathbf{A}}\right]$

## back
$\left[\frac{\partial f}{\partial \mathbf{A}}\right] + \left[\frac{\partial f}{\partial \mathbf{A}}\right]^T - \text{diag}\left[\frac{\partial f}{\partial \mathbf{A}}\right]$

## conditions
$f : \mathbb{R}^{n \times n} \to \mathbb{R}$ differentiable, so $\mathbf{A}$ is the argument $f$ is being varied in; $\mathbf{A} = \mathbf{A}^T$, varied over $A_{ij}$ with $i \le j$ only, the rest following by symmetry; $\left[\frac{\partial f}{\partial \mathbf{A}}\right]$ is the same derivative of the same $f$ taken with all $n^2$ entries varied independently; $\text{diag}(\mathbf{M})$ is $\mathbf{M}$ with the off-diagonal zeroed. Denominator layout.

## prose
Off-diagonal entries of a symmetric $\mathbf{A}$ move in pairs, so their two partial derivatives add; the diagonal moves alone, and $\text{diag}$ removes the double count.

## uses
Fitting a covariance or kernel matrix to data (maximum likelihood, EM).

## proof
Symmetry makes the structure matrix $\mathbf{S}^{ij} = \mathbf{J}^{ij} + \mathbf{J}^{ji} - \mathbf{J}^{ij}\mathbf{J}^{ij}$, which is $\mathbf{J}^{ij} + \mathbf{J}^{ji}$ off the diagonal and $\mathbf{J}^{ii}$ on it. Substituting it into $\frac{df}{dA_{ij}} = \text{Tr}\left[\left[\frac{\partial f}{\partial \mathbf{A}}\right]^T \mathbf{S}^{ij}\right]$ picks out entry $(i,j)$ plus entry $(j,i)$, less the diagonal term that would otherwise be counted twice.
