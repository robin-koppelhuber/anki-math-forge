---
uid: 7e49f8
type: identity
status: approved
content_hash: f4b57bc3f3758383
source: "Matrix Cookbook §2.2, p. 10"
unit: "matrix-cookbook:2.2:p10y321"
frequency: rare
derivation: short
tags: [derivatives, inverse, chain-rule]
verify: true
---

## front
$\frac{\partial J}{\partial \mathbf{A}}$ in terms of $\frac{\partial J}{\partial \mathbf{W}}$, where $\mathbf{W}=\mathbf{A}^{-1}$

## back
$-\mathbf{A}^{-\top}\frac{\partial J}{\partial \mathbf{W}}\mathbf{A}^{-\top}$

## conditions
$\mathbf{A} \in \mathbb{R}^{n \times n}$ invertible;
$J : \mathbb{R}^{n \times n} \to \mathbb{R}$. Denominator layout.

## prose
A gradient crossing an inversion is conjugated by $\mathbf{A}^{-\top}$ on both sides and flipped in sign, which is how a gradient in a covariance converts to one in its inverse (the precision matrix).

## proof
$d\mathbf{W} = -\mathbf{A}^{-1}(d\mathbf{A})\mathbf{A}^{-1}$, so
$dJ = \operatorname{Tr}\big((\partial J/\partial\mathbf{W})^\top d\mathbf{W}\big) = -\operatorname{Tr}\big(\mathbf{A}^{-1}(\partial J/\partial\mathbf{W})^\top\mathbf{A}^{-1}\, d\mathbf{A}\big)$;
transposing the bracket gives the result.

## verify
```python
A = invertible(4)
C = randn(4, 4)
Ai = np.linalg.inv(A)
lhs = grad(lambda M: np.trace(C @ np.linalg.inv(M)), A)
gW = grad(lambda W: np.trace(C @ W), Ai)
rhs = -Ai.T @ gW @ Ai.T
```

## notes
states, and differentiability of $J$, which the front presupposes by writing
its derivative. Scalar-valuedness is kept as the signature
$J : \mathbb{R}^{n \times n} \to \mathbb{R}$, because it is what makes both
gradients matrices.
