---
uid: de65cb
type: identity
status: approved
content_hash: 2801a1d386b21154
source: "Matrix Cookbook §3.1, eq. 151, p. 17"
unit: "matrix-cookbook:3.1:151"
gist: the inverse in terms of the adjugate
frequency: common
derivation: short
requires: [c49127]
tags: [inverse, cofactor, determinant]
verify: true
---

## front
$\mathbf{A}^{-1}$ in terms of $\text{adj}(\mathbf{A})$

## back
$\frac{1}{\det(\mathbf{A})}\,\text{adj}(\mathbf{A})$

## conditions
$\mathbf{A} \in \mathbb{C}^{n \times n}$; $\text{adj}(\mathbf{A})$ the adjugate; $\det(\mathbf{A}) \neq 0$.

## prose
Every entry of $\mathbf{A}^{-1}$ is a signed $(n-1) \times (n-1)$ determinant divided by $\det(\mathbf{A})$, which is where Cramer's rule comes from.

## verify
```python
A = invertible(4)
n = A.shape[0]
cof = np.array([[(-1) ** (i + j) * np.linalg.det(np.delete(np.delete(A, i, 0), j, 1))
                 for j in range(n)] for i in range(n)])
lhs = np.linalg.inv(A)
rhs = cof.T / np.linalg.det(A)
```
