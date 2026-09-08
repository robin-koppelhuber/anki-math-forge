---
uid: 4f76f8
type: identity
status: approved
content_hash: 3518e0477002a2c9
source: "Matrix Cookbook §2, eq. 32, p. 8"
unit: "matrix-cookbook:2:32"
frequency: common
derivation: definitional
tags: [derivatives, index-notation]
verify: false
---

## front
$\frac{\partial X_{kl}}{\partial X_{ij}}$

## back
$\delta_{ik}\delta_{lj}$

## conditions
$\mathbf{X} \in \mathbb{R}^{m \times n}$; entries of $\mathbf{X}$
algebraically independent.

## prose
Here $\delta_{pq}$ is $1$ when $p = q$ and $0$ otherwise, so the answer is $1$ exactly when $(k,l) = (i,j)$ (the Kronecker delta).

Structure on $\mathbf{X}$ (symmetry, a Toeplitz pattern) ties entries
together and changes the answer.

## notes
crop; every identity in chapter 2 rests on it.
