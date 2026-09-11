---
uid: ff1502
type: identity
status: approved
content_hash: 65d9c6edd37da574
source: "Matrix Cookbook §2.5, eq. 121, p. 13"
unit: "matrix-cookbook:2.5:121"
frequency: common
derivation: short
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}^k)$

## back
$k(\mathbf{X}^{k-1})^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$; $k \in \mathbb{Z}_{>0}$. Denominator layout.

## prose
The matrix analogue of $(x^k)' = k x^{k-1}$.

## proof
$d\,\text{Tr}(\mathbf{X}^k) = \sum_{r=0}^{k-1}\text{Tr}(\mathbf{X}^r d\mathbf{X}\,\mathbf{X}^{k-1-r}) = k\,\text{Tr}(\mathbf{X}^{k-1} d\mathbf{X})$, the $k$ terms being cyclic rotations of one another.

## verify
```python
X = randn(4, 4)
lhs = grad(lambda M: np.trace(np.linalg.matrix_power(M, 3)), X)
rhs = 3 * np.linalg.matrix_power(X, 2).T
```
