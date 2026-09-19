---
uid: "77e454"
type: identity
status: approved
content_hash: 5aec95d004d99ccb
source: "Matrix Cookbook §2.5, eq. 122, p. 13"
unit: "matrix-cookbook:2.5:122"
gist: the derivative of the trace of A times a power
frequency: rare
derivation: short
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{A}\mathbf{X}^k)$

## back
$\sum_{r=0}^{k-1}(\mathbf{X}^r\mathbf{A}\mathbf{X}^{k-r-1})^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$; $k$ a positive integer. Denominator layout.

## prose
The sum does not collapse the way it does for $\text{Tr}(\mathbf{X}^k)$, because $\mathbf{A}$ blocks the cyclic rotation that would make the terms equal.

## proof
$d\,\text{Tr}(\mathbf{A}\mathbf{X}^k) = \sum_{r=0}^{k-1}\text{Tr}(\mathbf{X}^{k-1-r}\mathbf{A}\mathbf{X}^{r} d\mathbf{X})$, one term per occurrence of $\mathbf{X}$.

## verify
```python
X = randn(4, 4)
A = randn(4, 4)
lhs = grad(lambda M: np.trace(A @ np.linalg.matrix_power(M, 3)), X)
rhs = sum((np.linalg.matrix_power(X, r) @ A @ np.linalg.matrix_power(X, 2 - r)).T
          for r in range(3))
```
