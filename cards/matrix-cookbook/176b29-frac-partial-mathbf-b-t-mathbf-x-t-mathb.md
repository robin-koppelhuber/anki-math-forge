---
uid: 176b29
type: identity
status: approved
content_hash: eb72e688e91d1651
source: "Matrix Cookbook §2.4, eq. 82, p. 11"
unit: "matrix-cookbook:2.4:82"
frequency: common
derivation: short
tags: [derivatives, quadratic-forms]
verify: true
---

## front
$\frac{\partial \mathbf{b}^T\mathbf{X}^T\mathbf{D}\mathbf{X}\mathbf{c}}{\partial \mathbf{X}}$

## back
$\mathbf{D}^T\mathbf{X}\mathbf{b}\mathbf{c}^T + \mathbf{D}\mathbf{X}\mathbf{c}\mathbf{b}^T$

## conditions
Denominator layout.

## proof
$df = \mathbf{b}^T\,d\mathbf{X}^T\,\mathbf{D}\mathbf{X}\mathbf{c}
+ \mathbf{b}^T\mathbf{X}^T\mathbf{D}\,d\mathbf{X}\,\mathbf{c}$; reading each
term as $\text{Tr}(\mathbf{G}^T\,d\mathbf{X})$ gives
$\mathbf{D}\mathbf{X}\mathbf{c}\mathbf{b}^T$ and
$\mathbf{D}^T\mathbf{X}\mathbf{b}\mathbf{c}^T$.

## verify
```python
X = randn(5, 3)
D = randn(5, 5)
b = randn(3, 1)
c = randn(3, 1)
lhs = grad(lambda M: (b.T @ M.T @ D @ M @ c)[0, 0], X)
rhs = D.T @ X @ b @ c.T + D @ X @ c @ b.T
```
