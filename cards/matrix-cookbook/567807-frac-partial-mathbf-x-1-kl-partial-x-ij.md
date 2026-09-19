---
uid: "567807"
type: identity
status: approved
content_hash: 5fd2daa8acf66acc
source: "Matrix Cookbook §2.2, eq. 60, p. 10"
unit: "matrix-cookbook:2.2:60"
gist: the derivative of one inverse entry by one entry
frequency: rare
derivation: short
tags: [derivatives, inverse, index-notation]
verify: true
---

## front
$\frac{\partial (\mathbf{X}^{-1})_{kl}}{\partial X_{ij}}$

## back
$-(\mathbf{X}^{-1})_{ki}(\mathbf{X}^{-1})_{jl}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible.

## proof
Put $\partial\mathbf{X}/\partial X_{ij} = \mathbf{J}^{ij}$, the matrix with a single $1$ in position $(i,j)$, into
$\partial\mathbf{Y}^{-1}/\partial x = -\mathbf{Y}^{-1}(\partial\mathbf{Y}/\partial x)\mathbf{Y}^{-1}$;
then $(\mathbf{X}^{-1}\mathbf{J}^{ij}\mathbf{X}^{-1})_{kl} = (\mathbf{X}^{-1})_{ki}(\mathbf{X}^{-1})_{jl}$.

## verify
```python
X = invertible(4)
Xi = np.linalg.inv(X)
k, l = 1, 3
lhs = grad(lambda M: np.linalg.inv(M)[k, l], X)
rhs = -np.outer(Xi[k, :], Xi[:, l])
```

## notes
no layout convention enters and the card carries no layout clause.
