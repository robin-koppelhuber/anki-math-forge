---
uid: bde58d
type: identity
status: approved
content_hash: e27952b22d2cfd70
source: "Matrix Cookbook §2.4, eq. 91, p. 11"
unit: "matrix-cookbook:2.4:91"
frequency: common
derivation: short
tags: [derivatives, matrix-powers]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\mathbf{a}^T\mathbf{X}^n\mathbf{b}$

## back
$\sum_{r=0}^{n-1}(\mathbf{X}^r)^T\mathbf{a}\mathbf{b}^T(\mathbf{X}^{n-1-r})^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{m \times m}$; $n \in \mathbb{Z}_{>0}$. Denominator layout.

## proof
$d(\mathbf{a}^T\mathbf{X}^n\mathbf{b}) = \sum_{r=0}^{n-1}
\text{Tr}(\mathbf{X}^{n-1-r}\mathbf{b}\mathbf{a}^T\mathbf{X}^r\,d\mathbf{X})$;
reading it as $\text{Tr}(\mathbf{G}^T\,d\mathbf{X})$ transposes each summand.

## verify
```python
n = 3
X = randn(4, 4)
a = randn(4, 1)
b = randn(4, 1)
lhs = grad(lambda M: (a.T @ np.linalg.matrix_power(M, n) @ b)[0, 0], X)
rhs = sum(
    np.linalg.matrix_power(X, r).T @ a @ b.T @ np.linalg.matrix_power(X, n - 1 - r).T
    for r in range(n)
)
```
